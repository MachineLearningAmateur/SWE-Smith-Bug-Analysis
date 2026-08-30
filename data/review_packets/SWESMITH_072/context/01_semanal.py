"""The semantic analyzer.

Bind names to definitions and do various other simple consistency
checks.  Populate symbol tables.  The semantic analyzer also detects
special forms which reuse generic syntax such as NamedTuple and
cast().  Multiple analysis iterations may be needed to analyze forward
references and import cycles. Each iteration "fills in" additional
bindings and references until everything has been bound.

For example, consider this program:

  x = 1
  y = x

Here semantic analysis would detect that the assignment 'x = 1'
defines a new variable, the type of which is to be inferred (in a
later pass; type inference or type checking is not part of semantic
analysis).  Also, it would bind both references to 'x' to the same
module-level variable (Var) node.  The second assignment would also
be analyzed, and the type of 'y' marked as being inferred.

Semantic analysis of types is implemented in typeanal.py.

See semanal_main.py for the top-level logic.

Some important properties:

* After semantic analysis is complete, no PlaceholderNode and
  PlaceholderType instances should remain. During semantic analysis,
  if we encounter one of these, the current target should be deferred.

* A TypeInfo is only created once we know certain basic information about
  a type, such as the MRO, existence of a Tuple base class (e.g., for named
  tuples), and whether we have a TypedDict. We use a temporary
  PlaceholderNode node in the symbol table if some such information is
  missing.

* For assignments, we only add a non-placeholder symbol table entry once
  we know the sort of thing being defined (variable, NamedTuple, type alias,
  etc.).

* Every part of the analysis step must support multiple iterations over
  the same AST nodes, and each iteration must be able to fill in arbitrary
  things that were missing or incomplete in previous iterations.

* Changes performed by the analysis need to be reversible, since mypy
  daemon strips and reuses existing ASTs (to improve performance and/or
  reduce memory use).
"""

from __future__ import annotations

from collections.abc import Collection, Iterable, Iterator
from contextlib import contextmanager
from typing import Any, Callable, Final, TypeVar, cast
from typing_extensions import TypeAlias as _TypeAlias, TypeGuard

from mypy import errorcodes as codes, message_registry
from mypy.constant_fold import constant_fold_expr
from mypy.errorcodes import PROPERTY_DECORATOR, ErrorCode
from mypy.errors import Errors, report_internal_error
from mypy.exprtotype import TypeTranslationError, expr_to_unanalyzed_type
from mypy.message_registry import ErrorMessage
from mypy.messages import (
    SUGGESTED_TEST_FIXTURES,
    TYPES_FOR_UNIMPORTED_HINTS,
    MessageBuilder,
    best_matches,
    pretty_seq,
)
from mypy.mro import MroError, calculate_mro
from mypy.nodes import (
    ARG_NAMED,
    ARG_POS,
    ARG_STAR2,
    CONTRAVARIANT,
    COVARIANT,
    GDEF,
    IMPLICITLY_ABSTRACT,
    INVARIANT,
    IS_ABSTRACT,
    LDEF,
    MDEF,
    NOT_ABSTRACT,
    PARAM_SPEC_KIND,
    REVEAL_LOCALS,
    REVEAL_TYPE,
    RUNTIME_PROTOCOL_DECOS,
    SYMBOL_FUNCBASE_TYPES,
    TYPE_VAR_KIND,
    TYPE_VAR_TUPLE_KIND,
    VARIANCE_NOT_READY,
    ArgKind,
    AssertStmt,
    AssertTypeExpr,
    AssignmentExpr,
    AssignmentStmt,
    AwaitExpr,
    Block,
    BreakStmt,
    BytesExpr,
    CallExpr,
    CastExpr,
    ClassDef,
    ComparisonExpr,
    ComplexExpr,
    ConditionalExpr,
    Context,
    ContinueStmt,
    DataclassTransformSpec,
    Decorator,
    DelStmt,
    DictExpr,
    DictionaryComprehension,
    EllipsisExpr,
    EnumCallExpr,
    Expression,
    ExpressionStmt,
    FakeExpression,
    FloatExpr,
    ForStmt,
    FuncBase,
    FuncDef,
    FuncItem,
    GeneratorExpr,
    GlobalDecl,
    IfStmt,
    Import,
    ImportAll,
    ImportBase,
    ImportFrom,
    IndexExpr,
    IntExpr,
    LambdaExpr,
    ListComprehension,
    ListExpr,
    Lvalue,
    MatchStmt,
    MemberExpr,
    MypyFile,
    NamedTupleExpr,
    NameExpr,
    Node,
    NonlocalDecl,
    OperatorAssignmentStmt,
    OpExpr,
    OverloadedFuncDef,
    OverloadPart,
    ParamSpecExpr,
    PassStmt,
    PlaceholderNode,
    PromoteExpr,
    RaiseStmt,
    RefExpr,
    ReturnStmt,
    RevealExpr,
    SetComprehension,
    SetExpr,
    SliceExpr,
    StarExpr,
    Statement,
    StrExpr,
    SuperExpr,
    SymbolNode,
    SymbolTable,
    SymbolTableNode,
    TempNode,
    TryStmt,
    TupleExpr,
    TypeAlias,
    TypeAliasExpr,
    TypeAliasStmt,
    TypeApplication,
    TypedDictExpr,
    TypeInfo,
    TypeParam,
    TypeVarExpr,
    TypeVarLikeExpr,
    TypeVarTupleExpr,
    UnaryExpr,
    Var,
    WhileStmt,
    WithStmt,
    YieldExpr,
    YieldFromExpr,
    get_member_expr_fullname,
    get_nongen_builtins,
    implicit_module_attrs,
    is_final_node,
    type_aliases,
    type_aliases_source_versions,
    typing_extensions_aliases,
)
from mypy.options import Options
from mypy.patterns import (
    AsPattern,
    ClassPattern,
    MappingPattern,
    OrPattern,
    SequencePattern,
    SingletonPattern,
    StarredPattern,
    ValuePattern,
)
from mypy.plugin import (
    ClassDefContext,
    DynamicClassDefContext,
    Plugin,
    SemanticAnalyzerPluginInterface,
)
from mypy.plugins import dataclasses as dataclasses_plugin
from mypy.reachability import (
    ALWAYS_FALSE,
    ALWAYS_TRUE,
    MYPY_FALSE,
    MYPY_TRUE,
    infer_condition_value,
    infer_reachability_of_if_statement,
    infer_reachability_of_match_statement,
)
from mypy.scope import Scope
from mypy.semanal_enum import EnumCallAnalyzer
from mypy.semanal_namedtuple import NamedTupleAnalyzer
from mypy.semanal_newtype import NewTypeAnalyzer
from mypy.semanal_shared import (
    ALLOW_INCOMPATIBLE_OVERRIDE,
    PRIORITY_FALLBACKS,
    SemanticAnalyzerInterface,
    calculate_tuple_fallback,
    find_dataclass_transform_spec,
    has_placeholder,
    parse_bool,
    require_bool_literal_argument,
    set_callable_name as set_callable_name,
)
from mypy.semanal_typeddict import TypedDictAnalyzer
from mypy.tvar_scope import TypeVarLikeScope
from mypy.typeanal import (
    SELF_TYPE_NAMES,
    FindTypeVarVisitor,
    TypeAnalyser,
    TypeVarDefaultTranslator,
    TypeVarLikeList,
    analyze_type_alias,
    check_for_explicit_any,
    detect_diverging_alias,
    find_self_type,
    fix_instance,
    has_any_from_unimported_type,
    no_subscript_builtin_alias,
    type_constructors,
    validate_instance,
)
from mypy.typeops import function_type, get_type_vars, try_getting_str_literals_from_type
from mypy.types import (
    ASSERT_TYPE_NAMES,
    DATACLASS_TRANSFORM_NAMES,
    DEPRECATED_TYPE_NAMES,
    FINAL_DECORATOR_NAMES,
    FINAL_TYPE_NAMES,
    IMPORTED_REVEAL_TYPE_NAMES,
    NEVER_NAMES,
    OVERLOAD_NAMES,
    OVERRIDE_DECORATOR_NAMES,
    PROTOCOL_NAMES,
    REVEAL_TYPE_NAMES,
    TPDICT_NAMES,
    TYPE_ALIAS_NAMES,
    TYPE_CHECK_ONLY_NAMES,
    TYPE_VAR_LIKE_NAMES,
    TYPED_NAMEDTUPLE_NAMES,
    UNPACK_TYPE_NAMES,
    AnyType,
    CallableType,
    FunctionLike,
    Instance,
    LiteralType,
    NoneType,
    Overloaded,
    Parameters,
    ParamSpecType,
    PlaceholderType,
    ProperType,
    TrivialSyntheticTypeTranslator,
    TupleType,
    Type,
    TypeAliasType,
    TypedDictType,
    TypeOfAny,
    TypeType,
    TypeVarId,
    TypeVarLikeType,
    TypeVarTupleType,
    TypeVarType,
    UnboundType,
    UnionType,
    UnpackType,
    get_proper_type,
    get_proper_types,
    has_type_vars,
    is_named_instance,
    remove_dups,
    type_vars_as_args,
)
from mypy.types_utils import is_invalid_recursive_alias, store_argument_type
from mypy.typevars import fill_typevars
from mypy.util import correct_relative_import, is_dunder, module_prefix, unmangle, unnamed_function
from mypy.visitor import NodeVisitor

T = TypeVar("T")


FUTURE_IMPORTS: Final = {
    "__future__.nested_scopes": "nested_scopes",
    "__future__.generators": "generators",
    "__future__.division": "division",
    "__future__.absolute_import": "absolute_import",
    "__future__.with_statement": "with_statement",
    "__future__.print_function": "print_function",
    "__future__.unicode_literals": "unicode_literals",
    "__future__.barry_as_FLUFL": "barry_as_FLUFL",
    "__future__.generator_stop": "generator_stop",
    "__future__.annotations": "annotations",
}


# Special cased built-in classes that are needed for basic functionality and need to be
# available very early on.
CORE_BUILTIN_CLASSES: Final = ["object", "bool", "function"]


# Python has several different scope/namespace kinds with subtly different semantics.
SCOPE_GLOBAL: Final = 0  # Module top level
SCOPE_CLASS: Final = 1  # Class body
SCOPE_FUNC: Final = 2  # Function or lambda
SCOPE_COMPREHENSION: Final = 3  # Comprehension or generator expression
SCOPE_ANNOTATION: Final = 4  # Annotation scopes for type parameters and aliases (PEP 695)


# Used for tracking incomplete references
Tag: _TypeAlias = int


class SemanticAnalyzer(
    NodeVisitor[None], SemanticAnalyzerInterface, SemanticAnalyzerPluginInterface
):
    """Semantically analyze parsed mypy files.

    The analyzer binds names and does various consistency checks for an
    AST. Note that type checking is performed as a separate pass.
    """

    __deletable__ = ["patches", "options", "cur_mod_node"]

    # Module name space
    modules: dict[str, MypyFile]
    # Global name space for current module
    globals: SymbolTable
    # Names declared using "global" (separate set for each scope)
    global_decls: list[set[str]]
    # Names declared using "nonlocal" (separate set for each scope)
    nonlocal_decls: list[set[str]]
    # Local names of function scopes; None for non-function scopes.
    locals: list[SymbolTable | None]
    # Type of each scope (SCOPE_*, indexes match locals)
    scope_stack: list[int]
    # Nested block depths of scopes
    block_depth: list[int]
    # TypeInfo of directly enclosing class (or None)
    _type: TypeInfo | None = None
    # Stack of outer classes (the second tuple item contains tvars).
    type_stack: list[TypeInfo | None]
    # Type variables bound by the current scope, be it class or function
    tvar_scope: TypeVarLikeScope
    # Per-module options
    options: Options

    # Stack of functions being analyzed
    function_stack: list[FuncItem]

    # Set to True if semantic analysis defines a name, or replaces a
    # placeholder definition. If some iteration makes no progress,
    # there can be at most one additional final iteration (see below).
    progress = False
    deferred = False  # Set to true if another analysis pass is needed
    incomplete = False  # Set to true if current module namespace is missing things
    # Is this the final iteration of semantic analysis (where we report
    # unbound names due to cyclic definitions and should not defer)?
    _final_iteration = False
    # These names couldn't be added to the symbol table due to incomplete deps.
    # Note that missing names are per module, _not_ per namespace. This means that e.g.
    # a missing name at global scope will block adding same name at a class scope.
    # This should not affect correctness and is purely a performance issue,
    # since it can cause unnecessary deferrals. These are represented as
    # PlaceholderNodes in the symbol table. We use this to ensure that the first
    # definition takes precedence even if it's incomplete.
    #
    # Note that a star import adds a special name '*' to the set, this blocks
    # adding _any_ names in the current file.
    missing_names: list[set[str]]
    # Callbacks that will be called after semantic analysis to tweak things.
    patches: list[tuple[int, Callable[[], None]]]
    loop_depth: list[int]  # Depth of breakable loops
    cur_mod_id = ""  # Current module id (or None) (phase 2)
    _is_stub_file = False  # Are we analyzing a stub file?
    _is_typeshed_stub_file = False  # Are we analyzing a typeshed stub file?
    imports: set[str]  # Imported modules (during phase 2 analysis)
    # Note: some imports (and therefore dependencies) might
    # not be found in phase 1, for example due to * imports.
    errors: Errors  # Keeps track of generated errors
    plugin: Plugin  # Mypy plugin for special casing of library features
    statement: Statement | None = None  # Statement/definition being analyzed

    # Mapping from 'async def' function definitions to their return type wrapped as a
    # 'Coroutine[Any, Any, T]'. Used to keep track of whether a function definition's
    # return type has already been wrapped, by checking if the function definition's
    # type is stored in this mapping and that it still matches.
    wrapped_coro_return_types: dict[FuncDef, Type] = {}

    def __init__(
        self,
        modules: dict[str, MypyFile],
        missing_modules: set[str],
        incomplete_namespaces: set[str],
        errors: Errors,
        plugin: Plugin,
    ) -> None:
        """Construct semantic analyzer.

        We reuse the same semantic analyzer instance across multiple modules.

        Args:
            modules: Global modules dictionary
            missing_modules: Modules that could not be imported encountered so far
            incomplete_namespaces: Namespaces that are being populated during semantic analysis
                (can contain modules and classes within the current SCC; mutated by the caller)
            errors: Report analysis errors using this instance
        """
        self.locals = [None]
        self.scope_stack = [SCOPE_GLOBAL]
        # Saved namespaces from previous iteration. Every top-level function/method body is
        # analyzed in several iterations until all names are resolved. We need to save
        # the local namespaces for the top level function and all nested functions between
        # these iterations. See also semanal_main.process_top_level_function().
        self.saved_locals: dict[
            FuncItem | GeneratorExpr | DictionaryComprehension, SymbolTable
        ] = {}
        self.imports = set()
        self._type = None
        self.type_stack = []
        # Are the namespaces of classes being processed complete?
        self.incomplete_type_stack: list[bool] = []
        self.tvar_scope = TypeVarLikeScope()
        self.function_stack = []
        self.block_depth = [0]
        self.loop_depth = [0]
        self.errors = errors
        self.modules = modules
        self.msg = MessageBuilder(errors, modules)
        self.missing_modules = missing_modules
        self.missing_names = [set()]
        # These namespaces are still in process of being populated. If we encounter a
        # missing name in these namespaces, we need to defer the current analysis target,
        # since it's possible that the name will be there once the namespace is complete.
        self.incomplete_namespaces = incomplete_namespaces
        self.all_exports: list[str] = []
        # Map from module id to list of explicitly exported names (i.e. names in __all__).
        self.export_map: dict[str, list[str]] = {}
        self.plugin = plugin
        # If True, process function definitions. If False, don't. This is used
        # for processing module top levels in fine-grained incremental mode.
        self.recurse_into_functions = True
        self.scope = Scope()

        # Trace line numbers for every file where deferral happened during analysis of
        # current SCC or top-level function.
        self.deferral_debug_context: list[tuple[str, int]] = []

        # This is needed to properly support recursive type aliases. The problem is that
        # Foo[Bar] could mean three things depending on context: a target for type alias,
        # a normal index expression (including enum index), or a type application.
        # The latter is particularly problematic as it can falsely create incomplete
        # refs while analysing rvalues of type aliases. To avoid this we first analyse
        # rvalues while temporarily setting this to True.
        self.basic_type_applications = False

        # Used to temporarily enable unbound type variables in some contexts. Namely,
        # in base class expressions, and in right hand sides of type aliases. Do not add
        # new uses of this, as this may cause leaking `UnboundType`s to type checking.
        self.allow_unbound_tvars = False

        # Used to pass information about current overload index to visit_func_def().
        self.current_overload_item: int | None = None

        # Used to track whether currently inside an except* block. This helps
        # to invoke errors when continue/break/return is used inside except* block.
        self.inside_except_star_block: bool = False
        # Used to track edge case when return is still inside except* if it enters a loop
        self.return_stmt_inside_except_star_block: bool = False

    # mypyc doesn't properly handle implementing an abstractproperty
    # with a regular attribute so we make them properties
    @property
    def type(self) -> TypeInfo | None:
        return self._type

    @property
    def is_stub_file(self) -> bool:
        return self._is_stub_file

    @property
    def is_typeshed_stub_file(self) -> bool:
        return self._is_typeshed_stub_file

    @property
    def final_iteration(self) -> bool:
        return self._final_iteration

    @contextmanager
    def allow_unbound_tvars_set(self) -> Iterator[None]:
        old = self.allow_unbound_tvars
        self.allow_unbound_tvars = True
        try:
            yield
        finally:
            self.allow_unbound_tvars = old

    @contextmanager
    def inside_except_star_block_set(
        self, value: bool, entering_loop: bool = False
    ) -> Iterator[None]:
        old = self.inside_except_star_block
        self.inside_except_star_block = value

        # Return statement would still be in except* scope if entering loops
        if not entering_loop:
            old_return_stmt_flag = self.return_stmt_inside_except_star_block
            self.return_stmt_inside_except_star_block = value

        try:
            yield
        finally:
            self.inside_except_star_block = old
            if not entering_loop:
                self.return_stmt_inside_except_star_block = old_return_stmt_flag

    #
    # Preparing module (performed before semantic analysis)
    #

    def prepare_file(self, file_node: MypyFile) -> None:
        """Prepare a freshly parsed file for semantic analysis."""
        if "builtins" in self.modules:
            file_node.names["__builtins__"] = SymbolTableNode(GDEF, self.modules["builtins"])
        if file_node.fullname == "builtins":
            self.prepare_builtins_namespace(file_node)
        if file_node.fullname == "typing":
            self.prepare_typing_namespace(file_node, type_aliases)
        if file_node.fullname == "typing_extensions":
            self.prepare_typing_namespace(file_node, typing_extensions_aliases)

    def prepare_typing_namespace(self, file_node: MypyFile, aliases: dict[str, str]) -> None:
        """Remove dummy alias definitions such as List = TypeAlias(object) from typing.

        They will be replaced with real aliases when corresponding targets are ready.
        """

        # This is all pretty unfortunate. typeshed now has a
        # sys.version_info check for OrderedDict, and we shouldn't
        # take it out, because it is correct and a typechecker should
        # use that as a source of truth. But instead we rummage
        # through IfStmts to remove the info first.  (I tried to
        # remove this whole machinery and ran into issues with the
        # builtins/typing import cycle.)
        def helper(defs: list[Statement]) -> None:
            for stmt in defs.copy():
                if isinstance(stmt, IfStmt):
                    for body in stmt.body:
                        helper(body.body)
                    if stmt.else_body:
                        helper(stmt.else_body.body)
                if (
                    isinstance(stmt, AssignmentStmt)
                    and len(stmt.lvalues) == 1
                    and isinstance(stmt.lvalues[0], NameExpr)
                ):
                    # Assignment to a simple name, remove it if it is a dummy alias.
                    if f"{file_node.fullname}.{stmt.lvalues[0].name}" in aliases:
                        defs.remove(stmt)

        helper(file_node.defs)

    def prepare_builtins_namespace(self, file_node: MypyFile) -> None:
        """Add certain special-cased definitions to the builtins module.

        Some definitions are too special or fundamental to be processed
        normally from the AST.
        """
        names = file_node.names

        # Add empty definition for core built-in classes, since they are required for basic
        # operation. These will be completed later on.
        for name in CORE_BUILTIN_CLASSES:
            cdef = ClassDef(name, Block([]))  # Dummy ClassDef, will be replaced later
            info = TypeInfo(SymbolTable(), cdef, "builtins")
            info._fullname = f"builtins.{name}"
            names[name] = SymbolTableNode(GDEF, info)

        bool_info = names["bool"].node
        assert isinstance(bool_info, TypeInfo)
        bool_type = Instance(bool_info, [])

        special_var_types: list[tuple[str, Type]] = [
            ("None", NoneType()),
            # reveal_type is a mypy-only function that gives an error with
            # the type of its arg.
            ("reveal_type", AnyType(TypeOfAny.special_form)),
            # reveal_locals is a mypy-only function that gives an error with the types of
            # locals
            ("reveal_locals", AnyType(TypeOfAny.special_form)),
            ("True", bool_type),
            ("False", bool_type),
            ("__debug__", bool_type),
        ]

        for name, typ in special_var_types:
            v = Var(name, typ)
            v._fullname = f"builtins.{name}"
            file_node.names[name] = SymbolTableNode(GDEF, v)

    #
    # Analyzing a target
    #

    def refresh_partial(
        self,
        node: MypyFile | FuncDef | OverloadedFuncDef,
        patches: list[tuple[int, Callable[[], None]]],
        final_iteration: bool,
        file_node: MypyFile,
        options: Options,
        active_type: TypeInfo | None = None,
    ) -> None:
        """Refresh a stale target in fine-grained incremental mode."""
        self.patches = patches
        self.deferred = False
        self.incomplete = False
        self._final_iteration = final_iteration
        self.missing_names[-1] = set()

        with self.file_context(file_node, options, active_type):
            if isinstance(node, MypyFile):
                self.refresh_top_level(node)
            else:
                self.recurse_into_functions = True
                self.accept(node)
        del self.patches

    def refresh_top_level(self, file_node: MypyFile) -> None:
        """Reanalyze a stale module top-level in fine-grained incremental mode."""
        self.recurse_into_functions = False
        self.add_implicit_module_attrs(file_node)
        for d in file_node.defs:
            self.accept(d)
        if file_node.fullname == "typing":
            self.add_builtin_aliases(file_node)
        if file_node.fullname == "typing_extensions":
            self.add_typing_extension_aliases(file_node)
        self.adjust_public_exports()
        self.export_map[self.cur_mod_id] = self.all_exports
        self.all_exports = []

    def add_implicit_module_attrs(self, file_node: MypyFile) -> None:
        """Manually add implicit definitions of module '__name__' etc."""
        str_type: Type | None = self.named_type_or_none("builtins.str")
        if str_type is None:
            str_type = UnboundType("builtins.str")
        inst: Type | None
        for name, t in implicit_module_attrs.items():
            if name == "__doc__":
                typ: Type = str_type
            elif name == "__path__":
                if not file_node.is_package_init_file():
                    continue
                # Need to construct the type ourselves, to avoid issues with __builtins__.list
                # not being subscriptable or typing.List not getting bound
                inst = self.named_type_or_none("builtins.list", [str_type])
                if inst is None:
                    assert not self.final_iteration, "Cannot find builtins.list to add __path__"
                    self.defer()
                    return
                typ = inst
            elif name == "__annotations__":
                inst = self.named_type_or_none(
                    "builtins.dict", [str_type, AnyType(TypeOfAny.special_form)]
                )
                if inst is None:
                    assert (
                        not self.final_iteration
                    ), "Cannot find builtins.dict to add __annotations__"
                    self.defer()
                    return
                typ = inst
            elif name == "__spec__":
                if self.options.use_builtins_fixtures:
                    inst = self.named_type_or_none("builtins.object")
                else:
                    inst = self.named_type_or_none("importlib.machinery.ModuleSpec")
                if inst is None:
                    if self.final_iteration:
                        inst = self.named_type_or_none("builtins.object")
                        assert inst is not None, "Cannot find builtins.object"
                    else:
                        self.defer()
                        return
                if file_node.name == "__main__":
                    # https://docs.python.org/3/reference/import.html#main-spec
                    inst = UnionType.make_union([inst, NoneType()])
                typ = inst
            else:
                assert t is not None, f"type should be specified for {name}"
                typ = UnboundType(t)

            existing = file_node.names.get(name)
            if existing is not None and not isinstance(existing.node, PlaceholderNode):
                # Already exists.
                continue

            an_type = self.anal_type(typ)
            if an_type:
                var = Var(name, an_type)
                var._fullname = self.qualified_name(name)
                var.is_ready = True
                self.add_symbol(name, var, dummy_context())
            else:
                self.add_symbol(
                    name,
                    PlaceholderNode(self.qualified_name(name), file_node, -1),
                    dummy_context(),
                )

    def add_builtin_aliases(self, tree: MypyFile) -> None:
        """Add builtin type aliases to typing module.

        For historical reasons, the aliases like `List = list` are not defined
        in typeshed stubs for typing module. Instead we need to manually add the
        corresponding nodes on the fly. We explicitly mark these aliases as normalized,
        so that a user can write `typing.List[int]`.
        """
        assert tree.fullname == "typing"
        for alias, target_name in type_aliases.items():
            if (
                alias in type_aliases_source_versions
                and type_aliases_source_versions[alias] > self.options.python_version
            ):
                # This alias is not available on this Python version.
                continue
            name = alias.split(".")[-1]
            if name in tree.names and not isinstance(tree.names[name].node, PlaceholderNode):
                continue
            self.create_alias(tree, target_name, alias, name)

    def add_typing_extension_aliases(self, tree: MypyFile) -> None:
        """Typing extensions module does contain some type aliases.

        We need to analyze them as such, because in typeshed
        they are just defined as `_Alias()` call.
        Which is not supported natively.
        """
        assert tree.fullname == "typing_extensions"

        for alias, target_name in typing_extensions_aliases.items():
            name = alias.split(".")[-1]
            if name in tree.names and isinstance(tree.names[name].node, TypeAlias):
                continue  # Do not reset TypeAliases on the second pass.

            # We need to remove any node that is there at the moment. It is invalid.
            tree.names.pop(name, None)

            # Now, create a new alias.
            self.create_alias(tree, target_name, alias, name)

    def create_alias(self, tree: MypyFile, target_name: str, alias: str, name: str) -> None:
        tag = self.track_incomplete_refs()
        n = self.lookup_fully_qualified_or_none(target_name)
        if n:
            if isinstance(n.node, PlaceholderNode):
                self.mark_incomplete(name, tree)
            else:
                # Found built-in class target. Create alias.
                target = self.named_type_or_none(target_name, [])
                assert target is not None
                # Transform List to List[Any], etc.
                fix_instance(
                    target, self.fail, self.note, disallow_any=False, options=self.options
                )
                alias_node = TypeAlias(
                    target,
                    alias,
                    line=-1,
                    column=-1,  # there is no context
                    no_args=True,
                    normalized=True,
                )
                self.add_symbol(name, alias_node, tree)
        elif self.found_incomplete_ref(tag):
            # Built-in class target may not ready yet -- defer.
            self.mark_incomplete(name, tree)
        else:
            # Test fixtures may be missing some builtin classes, which is okay.
            # Kill the placeholder if there is one.
            if name in tree.names:
                assert isinstance(tree.names[name].node, PlaceholderNode)
                del tree.names[name]

    def adjust_public_exports(self) -> None:
        """Adjust the module visibility of globals due to __all__."""
        if "__all__" in self.globals:
            for name, g in self.globals.items():
                # Being included in __all__ explicitly exports and makes public.
                if name in self.all_exports:
                    g.module_public = True
                    g.module_hidden = False
                # But when __all__ is defined, and a symbol is not included in it,
                # it cannot be public.
                else:
                    g.module_public = False

    @contextmanager
    def file_context(
        self, file_node: MypyFile, options: Options, active_type: TypeInfo | None = None
    ) -> Iterator[None]:
        """Configure analyzer for analyzing targets within a file/class.

        Args:
            file_node: target file
            options: options specific to the file
            active_type: must be the surrounding class to analyze method targets
        """
        scope = self.scope
        self.options = options
        self.errors.set_file(file_node.path, file_node.fullname, scope=scope, options=options)
        self.cur_mod_node = file_node
        self.cur_mod_id = file_node.fullname
        with scope.module_scope(self.cur_mod_id):
            self._is_stub_file = file_node.path.lower().endswith(".pyi")
            self._is_typeshed_stub_file = file_node.is_typeshed_file(options)
            self.globals = file_node.names
            self.tvar_scope = TypeVarLikeScope()

            self.named_tuple_analyzer = NamedTupleAnalyzer(options, self, self.msg)
            self.typed_dict_analyzer = TypedDictAnalyzer(options, self, self.msg)
            self.enum_call_analyzer = EnumCallAnalyzer(options, self)
            self.newtype_analyzer = NewTypeAnalyzer(options, self, self.msg)

            # Counter that keeps track of references to undefined things potentially caused by
            # incomplete namespaces.
            self.num_incomplete_refs = 0

            if active_type:
                enclosing_fullname = active_type.fullname.rsplit(".", 1)[0]
                if "." in enclosing_fullname:
                    enclosing_node = self.lookup_fully_qualified_or_none(enclosing_fullname)
                    if enclosing_node and isinstance(enclosing_node.node, TypeInfo):
                        self._type = enclosing_node.node
                self.push_type_args(active_type.defn.type_args, active_type.defn)
                self.incomplete_type_stack.append(False)
                scope.enter_class(active_type)
                self.enter_class(active_type.defn.info)
                for tvar in active_type.defn.type_vars:
                    self.tvar_scope.bind_existing(tvar)

            yield

            if active_type:
                scope.leave_class()
                self.leave_class()
                self._type = None
                self.incomplete_type_stack.pop()
                self.pop_type_args(active_type.defn.type_args)
        del self.options

    #
    # Functions
    #

    def visit_func_def(self, defn: FuncDef) -> None:
        self.statement = defn

        # Visit default values because they may contain assignment expressions.
        for arg in defn.arguments:
            if arg.initializer:
                arg.initializer.accept(self)

        defn.is_conditional = self.block_depth[-1] > 0

        # Set full names even for those definitions that aren't added
        # to a symbol table. For example, for overload items.
        defn._fullname = self.qualified_name(defn.name)

        # We don't add module top-level functions to symbol tables
        # when we analyze their bodies in the second phase on analysis,
        # since they were added in the first phase. Nested functions
        # get always added, since they aren't separate targets.
        if not self.recurse_into_functions or len(self.function_stack) > 0:
            if not defn.is_decorated and not defn.is_overload:
                self.add_function_to_symbol_table(defn)

        if not self.recurse_into_functions:
            return

        with self.scope.function_scope(defn):
            with self.inside_except_star_block_set(value=False):
                self.analyze_func_def(defn)

    def function_fullname(self, fullname: str) -> str:
        if self.current_overload_item is None:
            return fullname
        return f"{fullname}#{self.current_overload_item}"

    def analyze_func_def(self, defn: FuncDef) -> None:
        if self.push_type_args(defn.type_args, defn) is None:
            self.defer(defn)
            return

        self.function_stack.append(defn)

        if defn.type:
            assert isinstance(defn.type, CallableType)
            has_self_type = self.update_function_type_variables(defn.type, defn)
        else:
            has_self_type = False

        self.function_stack.pop()

        if self.is_class_scope():
            # Method definition
            assert self.type is not None
            defn.info = self.type
            if defn.type is not None and defn.name in ("__init__", "__init_subclass__"):
                assert isinstance(defn.type, CallableType)
                if isinstance(get_proper_type(defn.type.ret_type), AnyType):
                    defn.type = defn.type.copy_modified(ret_type=NoneType())
            self.prepare_method_signature(defn, self.type, has_self_type)

        # Analyze function signature
        fullname = self.function_fullname(defn.fullname)
        with self.tvar_scope_frame(self.tvar_scope.method_frame(fullname)):
            if defn.type:
                self.check_classvar_in_signature(defn.type)
                assert isinstance(defn.type, CallableType)
                # Signature must be analyzed in the surrounding scope so that
                # class-level imported names and type variables are in scope.
                analyzer = self.type_analyzer()
                tag = self.track_incomplete_refs()
                result = analyzer.visit_callable_type(defn.type, nested=False, namespace=fullname)
                # Don't store not ready types (including placeholders).
                if self.found_incomplete_ref(tag) or has_placeholder(result):
                    self.defer(defn)
                    self.pop_type_args(defn.type_args)
                    return
                assert isinstance(result, ProperType)
                if isinstance(result, CallableType):
                    # type guards need to have a positional argument, to spec
                    skip_self = self.is_class_scope() and not defn.is_static
                    if result.type_guard and ARG_POS not in result.arg_kinds[skip_self:]:
                        self.fail(
                            "TypeGuard functions must have a positional argument",
                            result,
                            code=codes.VALID_TYPE,
                        )
                        # in this case, we just kind of just ... remove the type guard.
                        result = result.copy_modified(type_guard=None)
                    if result.type_is and ARG_POS not in result.arg_kinds[skip_self:]:
                        self.fail(
                            '"TypeIs" functions must have a positional argument',
                            result,
                            code=codes.VALID_TYPE,
                        )
                        result = result.copy_modified(type_is=None)

                    result = self.remove_unpack_kwargs(defn, result)
                    if has_self_type and self.type is not None:
                        info = self.type
                        if info.self_type is not None:
                            result.variables = [info.self_type] + list(result.variables)
                defn.type = result
                self.add_type_alias_deps(analyzer.aliases_used)
                self.check_function_signature(defn)
                if isinstance(defn, FuncDef):
                    assert isinstance(defn.type, CallableType)
                    defn.type = set_callable_name(defn.type, defn)

        self.analyze_arg_initializers(defn)
        self.analyze_function_body(defn)

        if self.is_class_scope():
            assert self.type is not None
            # Mark protocol methods with empty bodies as implicitly abstract.
            # This makes explicit protocol subclassing type-safe.
            if (
                self.type.is_protocol
                and not self.is_stub_file  # Bodies in stub files are always empty.
                and (not isinstance(self.scope.function, OverloadedFuncDef) or defn.is_property)
                and defn.abstract_status != IS_ABSTRACT
                and is_trivial_body(defn.body)
            ):
                defn.abstract_status = IMPLICITLY_ABSTRACT
            if (
                is_trivial_body(defn.body)
                and not self.is_stub_file
                and defn.abstract_status != NOT_ABSTRACT
            ):
                defn.is_trivial_body = True

        if (
            defn.is_coroutine
            and isinstance(defn.type, CallableType)
            and self.wrapped_coro_return_types.get(defn) != defn.type
        ):
            if defn.is_async_generator:
                # Async generator types are handled elsewhere
                pass
            else:
                # A coroutine defined as `async def foo(...) -> T: ...`
                # has external return type `Coroutine[Any, Any, T]`.
                any_type = AnyType(TypeOfAny.special_form)
                ret_type = self.named_type_or_none(
                    "typing.Coroutine", [any_type, any_type, defn.type.ret_type]
                )
                assert ret_type is not None, "Internal error: typing.Coroutine not found"
                defn.type = defn.type.copy_modified(ret_type=ret_type)
                self.wrapped_coro_return_types[defn] = defn.type

        self.pop_type_args(defn.type_args)

    def remove_unpack_kwargs(self, defn: FuncDef, typ: CallableType) -> CallableType:
        if not typ.arg_kinds or typ.arg_kinds[-1] is not ArgKind.ARG_STAR2:
            return typ
        last_type = typ.arg_types[-1]
        if not isinstance(last_type, UnpackType):
            return typ
        last_type = get_proper_type(last_type.type)
        if not isinstance(last_type, TypedDictType):
            self.fail("Unpack item in ** argument must be a TypedDict", last_type)
            new_arg_types = typ.arg_types[:-1] + [AnyType(TypeOfAny.from_error)]
            return typ.copy_modified(arg_types=new_arg_types)
        overlap = set(typ.arg_names) & set(last_type.items)
        # It is OK for TypedDict to have a key named 'kwargs'.
        overlap.discard(typ.arg_names[-1])
        if overlap:
            overlapped = ", ".join([f'"{name}"' for name in overlap])
            self.fail(f"Overlap between argument names and ** TypedDict items: {overlapped}", defn)
            new_arg_types = typ.arg_types[:-1] + [AnyType(TypeOfAny.from_error)]
            return typ.copy_modified(arg_types=new_arg_types)
        # OK, everything looks right now, mark the callable type as using unpack.
        new_arg_types = typ.arg_types[:-1] + [last_type]
        return typ.copy_modified(arg_types=new_arg_types, unpack_kwargs=True)

    def prepare_method_signature(self, func: FuncDef, info: TypeInfo, has_self_type: bool) -> None:
        """Check basic signature validity and tweak annotation of self/cls argument."""
        # Only non-static methods are special, as well as __new__.
        functype = func.type
        if func.name == "__new__":
            func.is_static = True
        if not func.is_static or func.name == "__new__":
            if func.name in ["__init_subclass__", "__class_getitem__"]:
                func.is_class = True
            if not func.arguments:
                self.fail(
                    'Method must have at least one argument. Did you forget the "self" argument?',
                    func,
                )
            elif isinstance(functype, CallableType):
                self_type = get_proper_type(functype.arg_types[0])
                if isinstance(self_type, AnyType):
                    if has_self_type:
                        assert self.type is not None and self.type.self_type is not None
                        leading_type: Type = self.type.self_type
                    else:
                        leading_type = fill_typevars(info)
                    if func.is_class or func.name == "__new__":
                        leading_type = self.class_type(leading_type)
                    func.type = replace_implicit_first_type(functype, leading_type)
                elif has_self_type and isinstance(func.unanalyzed_type, CallableType):
                    if not isinstance(get_proper_type(func.unanalyzed_type.arg_types[0]), AnyType):
                        if self.is_expected_self_type(
                            self_type, func.is_class or func.name == "__new__"
                        ):
                            # This error is off by default, since it is explicitly allowed
                            # by the PEP 673.
                            self.fail(
                                'Redundant "Self" annotation for the first method argument',
                                func,
                                code=codes.REDUNDANT_SELF_TYPE,
                            )
                        else:
                            self.fail(
                                "Method cannot have explicit self annotation and Self type", func
                            )
        elif has_self_type:
            self.fail("Static methods cannot use Self type", func)

    def is_expected_self_type(self, typ: Type, is_classmethod: bool) -> bool:
        """Does this (analyzed or not) type represent the expected Self type for a method?"""
        assert self.type is not None
        typ = get_proper_type(typ)
        if is_classmethod:
            if isinstance(typ, TypeType):
                return self.is_expected_self_type(typ.item, is_classmethod=False)
            if isinstance(typ, UnboundType):
                sym = self.lookup_qualified(typ.name, typ, suppress_errors=True)
                if (
                    sym is not None
                    and (
                        sym.fullname == "typing.Type"
                        or (
                            sym.fullname == "builtins.type"
                            and (
                                self.is_stub_file
                                or self.is_future_flag_set("annotations")
                                or self.options.python_version >= (3, 9)
                            )
                        )
                    )
                    and typ.args
                ):
                    return self.is_expected_self_type(typ.args[0], is_classmethod=False)
            return False
        if isinstance(typ, TypeVarType):
            return typ == self.type.self_type
        if isinstance(typ, UnboundType):
            sym = self.lookup_qualified(typ.name, typ, suppress_errors=True)
            return sym is not None and sym.fullname in SELF_TYPE_NAMES
        return False

    def set_original_def(self, previous: Node | None, new: FuncDef | Decorator) -> bool:
        """If 'new' conditionally redefine 'previous', set 'previous' as original

        We reject straight redefinitions of functions, as they are usually
        a programming error. For example:

          def f(): ...
          def f(): ...  # Error: 'f' redefined
        """
        if isinstance(new, Decorator):
            new = new.func
        if (
            isinstance(previous, (FuncDef, Decorator))
            and unnamed_function(new.name)
            and unnamed_function(previous.name)
        ):
            return True
        if isinstance(previous, (FuncDef, Var, Decorator)) and new.is_conditional:
            new.original_def = previous
            return True
        else:
            return False

    def update_function_type_variables(self, fun_type: CallableType, defn: FuncItem) -> bool:
        """Make any type variables in the signature of defn explicit.

        Update the signature of defn to contain type variable definitions
        if defn is generic. Return True, if the signature contains typing.Self
        type, or False otherwise.
        """
        fullname = self.function_fullname(defn.fullname)
        with self.tvar_scope_frame(self.tvar_scope.method_frame(fullname)):
            a = self.type_analyzer()
            fun_type.variables, has_self_type = a.bind_function_type_variables(fun_type, defn)
            if has_self_type and self.type is not None:
                self.setup_self_type()
            if defn.type_args:
                bound_fullnames = {v.fullname for v in fun_type.variables}
                declared_fullnames = {self.qualified_name(p.name) for p in defn.type_args}
                extra = sorted(bound_fullnames - declared_fullnames)
                if extra:
                    self.msg.type_parameters_should_be_declared(
                        [n.split(".")[-1] for n in extra], defn
                    )
            return has_self_type

    def setup_self_type(self) -> None:
        """Setup a (shared) Self type variable for current class.

        We intentionally don't add it to the class symbol table,
        so it can be accessed only by mypy and will not cause
        clashes with user defined names.
        """
        assert self.type is not None
        info = self.type
        if info.self_type is not None:
            if has_placeholder(info.self_type.upper_bound):
                # Similar to regular (user defined) type variables.
                self.process_placeholder(
                    None,
                    "Self upper bound",
                    info,
                    force_progress=info.self_type.upper_bound != fill_typevars(info),
                )
            else:
                return
        info.self_type = TypeVarType(
            "Self",
            f"{info.fullname}.Self",
            id=TypeVarId(0),  # 0 is a special value for self-types.
            values=[],
            upper_bound=fill_typevars(info),
            default=AnyType(TypeOfAny.from_omitted_generics),
        )

    def visit_overloaded_func_def(self, defn: OverloadedFuncDef) -> None:
        self.statement = defn
        self.add_function_to_symbol_table(defn)

        if not self.recurse_into_functions:
            return

        # NB: Since _visit_overloaded_func_def will call accept on the
        # underlying FuncDefs, the function might get entered twice.
        # This is fine, though, because only the outermost function is
        # used to compute targets.
        with self.scope.function_scope(defn):
            self.analyze_overloaded_func_def(defn)

    @contextmanager
    def overload_item_set(self, item: int | None) -> Iterator[None]:
        self.current_overload_item = item
        try:
            yield
        finally:
            self.current_overload_item = None

    def analyze_overloaded_func_def(self, defn: OverloadedFuncDef) -> None:
        # OverloadedFuncDef refers to any legitimate situation where you have
        # more than one declaration for the same function in a row.  This occurs
        # with a @property with a setter or a deleter, and for a classic
        # @overload.

        defn._fullname = self.qualified_name(defn.name)
        # TODO: avoid modifying items.
        defn.items = defn.unanalyzed_items.copy()

        first_item = defn.items[0]
        first_item.is_overload = True
        with self.overload_item_set(0):
            first_item.accept(self)

        if isinstance(first_item, Decorator) and first_item.func.is_property:
            # This is a property.
            first_item.func.is_overload = True
            self.analyze_property_with_multi_part_definition(defn)
            typ = function_type(first_item.func, self.named_type("builtins.function"))
            assert isinstance(typ, CallableType)
            types = [typ]
        else:
            # This is an a normal overload. Find the item signatures, the
            # implementation (if outside a stub), and any missing @overload
            # decorators.
            types, impl, non_overload_indexes = self.analyze_overload_sigs_and_impl(defn)
            defn.impl = impl
            if non_overload_indexes:
                self.handle_missing_overload_decorators(
                    defn, non_overload_indexes, some_overload_decorators=len(types) > 0
                )
            # If we found an implementation, remove it from the overload item list,
            # as it's special.
            if impl is not None:
                assert impl is defn.items[-1]
                defn.items = defn.items[:-1]
            elif not non_overload_indexes:
                self.handle_missing_overload_implementation(defn)

        if types and not any(
            # If some overload items are decorated with other decorators, then
            # the overload type will be determined during type checking.
            isinstance(it, Decorator) and len(it.decorators) > 1
            for it in defn.items
        ):
            # TODO: should we enforce decorated overloads consistency somehow?
            # Some existing code uses both styles:
            #   * Put decorator only on implementation, use "effective" types in overloads
            #   * Put decorator everywhere, use "bare" types in overloads.
            defn.type = Overloaded(types)
            defn.type.line = defn.line

        if not defn.items:
            # It was not a real overload after all, but function redefinition. We've
            # visited the redefinition(s) already.
            if not defn.impl:
                # For really broken overloads with no items and no implementation we need to keep
                # at least one item to hold basic information like function name.
                defn.impl = defn.unanalyzed_items[-1]
            return

        # We know this is an overload def. Infer properties and perform some checks.
        self.process_deprecated_overload(defn)
        self.process_final_in_overload(defn)
        self.process_static_or_class_method_in_overload(defn)
        self.process_overload_impl(defn)

    def process_deprecated_overload(self, defn: OverloadedFuncDef) -> None:
        if defn.is_property:
            return

        if isinstance(impl := defn.impl, Decorator) and (
            (deprecated := impl.func.deprecated) is not None
        ):
            defn.deprecated = deprecated
            for item in defn.items:
                if isinstance(item, Decorator):
                    item.func.deprecated = deprecated

        for item in defn.items:
            deprecation = False
            if isinstance(item, Decorator):
                for d in item.decorators:
                    if deprecation and refers_to_fullname(d, OVERLOAD_NAMES):
                        self.msg.note("@overload should be placed before @deprecated", d)
                    elif (deprecated := self.get_deprecated(d)) is not None:
                        deprecation = True
                        if isinstance(typ := item.func.type, CallableType):
                            typestr = f" {typ} "
                        else:
                            typestr = " "
                        item.func.deprecated = (
                            f"overload{typestr}of function {defn.fullname} is deprecated: "
                            f"{deprecated}"
                        )

    @staticmethod
    def get_deprecated(expression: Expression) -> str | None:
        if (
            isinstance(expression, CallExpr)
            and refers_to_fullname(expression.callee, DEPRECATED_TYPE_NAMES)
            and (len(args := expression.args) >= 1)
            and isinstance(deprecated := args[0], StrExpr)
        ):
            return deprecated.value
        return None

    def process_overload_impl(self, defn: OverloadedFuncDef) -> None:
        """Set flags for an overload implementation.

        Currently, this checks for a trivial body in protocols classes,
        where it makes the method implicitly abstract.
        """
        if defn.impl is None:
            return
        impl = defn.impl if isinstance(defn.impl, FuncDef) else defn.impl.func
        if is_trivial_body(impl.body) and self.is_class_scope() and not self.is_stub_file:
            assert self.type is not None
            if self.type.is_protocol:
                impl.abstract_status = IMPLICITLY_ABSTRACT
            if impl.abstract_status != NOT_ABSTRACT:
                impl.is_trivial_body = True

    def analyze_overload_sigs_and_impl(
        self, defn: OverloadedFuncDef
    ) -> tuple[list[CallableType], OverloadPart | None, list[int]]:
        """Find overload signatures, the implementation, and items with missing @overload.

        Assume that the first was already analyzed. As a side effect:
        analyzes remaining items and updates 'is_overload' flags.
        """
        types = []
        non_overload_indexes = []
        impl: OverloadPart | None = None
        for i, item in enumerate(defn.items):
            if i != 0:
                # Assume that the first item was already visited
                item.is_overload = True
                with self.overload_item_set(i if i < len(defn.items) - 1 else None):
                    item.accept(self)
            # TODO: support decorated overloaded functions properly
            if isinstance(item, Decorator):
                callable = function_type(item.func, self.named_type("builtins.function"))
                assert isinstance(callable, CallableType)
                if not any(refers_to_fullname(dec, OVERLOAD_NAMES) for dec in item.decorators):
                    if i == len(defn.items) - 1 and not self.is_stub_file:
                        # Last item outside a stub is impl
                        impl = item
                    else:
                        # Oops it wasn't an overload after all. A clear error
                        # will vary based on where in the list it is, record
                        # that.
                        non_overload_indexes.append(i)
                else:
                    item.func.is_overload = True
                    types.append(callable)
                    if item.var.is_property:
                        self.fail("An overload can not be a property", item)
                # If any item was decorated with `@override`, the whole overload
                # becomes an explicit override.
                defn.is_explicit_override |= item.func.is_explicit_override
            elif isinstance(item, FuncDef):
                if i == len(defn.items) - 1 and not self.is_stub_file:
                    impl = item
                else:
                    non_overload_indexes.append(i)
        return types, impl, non_overload_indexes

    def handle_missing_overload_decorators(
        self,
        defn: OverloadedFuncDef,
        non_overload_indexes: list[int],
        some_overload_decorators: bool,
    ) -> None:
        """Generate errors for overload items without @overload.

        Side effect: remote non-overload items.
        """
        if some_overload_decorators:
            # Some of them were overloads, but not all.
            for idx in non_overload_indexes:
                if self.is_stub_file:
                    self.fail(
                        "An implementation for an overloaded function "
                        "is not allowed in a stub file",
                        defn.items[idx],
                    )
                else:
                    self.fail(
                        "The implementation for an overloaded function must come last",
                        defn.items[idx],
                    )
        else:
            for idx in non_overload_indexes[1:]:
                self.name_already_defined(defn.name, defn.items[idx], defn.items[0])
            if defn.impl:
                self.name_already_defined(defn.name, defn.impl, defn.items[0])
        # Remove the non-overloads
        for idx in reversed(non_overload_indexes):
            del defn.items[idx]

    def handle_missing_overload_implementation(self, defn: OverloadedFuncDef) -> None:
        """Generate error about missing overload implementation (only if needed)."""
        if not self.is_stub_file:
            if self.type and self.type.is_protocol and not self.is_func_scope():
                # An overloaded protocol method doesn't need an implementation,
                # but if it doesn't have one, then it is considered abstract.
                for item in defn.items:
                    if isinstance(item, Decorator):
                        item.func.abstract_status = IS_ABSTRACT
                    else:
                        item.abstract_status = IS_ABSTRACT
            else:
                # TODO: also allow omitting an implementation for abstract methods in ABCs?
                self.fail(
                    "An overloaded function outside a stub file must have an implementation",
                    defn,
                    code=codes.NO_OVERLOAD_IMPL,
                )

    def process_final_in_overload(self, defn: OverloadedFuncDef) -> None:
        """Detect the @final status of an overloaded function (and perform checks)."""
        # If the implementation is marked as @final (or the first overload in
        # stubs), then the whole overloaded definition if @final.
        if any(item.is_final for item in defn.items):
            # We anyway mark it as final because it was probably the intention.
            defn.is_final = True
            # Only show the error once per overload
            bad_final = next(ov for ov in defn.items if ov.is_final)
            if not self.is_stub_file:
                self.fail("@final should be applied only to overload implementation", bad_final)
            elif any(item.is_final for item in defn.items[1:]):
                bad_final = next(ov for ov in defn.items[1:] if ov.is_final)
                self.fail(
                    "In a stub file @final must be applied only to the first overload", bad_final
                )
        if defn.impl is not None and defn.impl.is_final:
            defn.is_final = True

    def process_static_or_class_method_in_overload(self, defn: OverloadedFuncDef) -> None:
        class_status = []
        static_status = []
        for item in defn.items:
            if isinstance(item, Decorator):
                inner = item.func
            elif isinstance(item, FuncDef):
                inner = item
            else:
                assert False, f"The 'item' variable is an unexpected type: {type(item)}"
            class_status.append(inner.is_class)
            static_status.append(inner.is_static)

        if defn.impl is not None:
            if isinstance(defn.impl, Decorator):
                inner = defn.impl.func
            elif isinstance(defn.impl, FuncDef):
                inner = defn.impl
            else:
                assert False, f"Unexpected impl type: {type(defn.impl)}"
            class_status.append(inner.is_class)
            static_status.append(inner.is_static)

        if len(set(class_status)) != 1:
            self.msg.overload_inconsistently_applies_decorator("classmethod", defn)
        elif len(set(static_status)) != 1:
            self.msg.overload_inconsistently_applies_decorator("staticmethod", defn)
        else:
            defn.is_class = class_status[0]
            defn.is_static = static_status[0]

    def analyze_property_with_multi_part_definition(self, defn: OverloadedFuncDef) -> None:
        """Analyze a property defined using multiple methods (e.g., using @x.setter).

        Assume that the first method (@property) has already been analyzed.
        """
        defn.is_property = True
        items = defn.items
        first_item = defn.items[0]
        assert isinstance(first_item, Decorator)
        deleted_items = []
        for i, item in enumerate(items[1:]):
            if isinstance(item, Decorator):
                if len(item.decorators) >= 1:
                    first_node = item.decorators[0]
                    if isinstance(first_node, MemberExpr):
                        if first_node.name == "setter":
                            # The first item represents the entire property.
                            first_item.var.is_settable_property = True
                            # Get abstractness from the original definition.
                            item.func.abstract_status = first_item.func.abstract_status
                        if first_node.name == "deleter":
                            item.func.abstract_status = first_item.func.abstract_status
                        for other_node in item.decorators[1:]:
                            other_node.accept(self)
                    else:
                        self.fail(
                            f"Only supported top decorator is @{first_item.func.name}.setter", item
                        )
                item.func.accept(self)
            else:
                self.fail(f'Unexpected definition for property "{first_item.func.name}"', item)
                deleted_items.append(i + 1)
        for i in reversed(deleted_items):
            del items[i]

        for item in items[1:]:
            if isinstance(item, Decorator):
                for d in item.decorators:
                    if (deprecated := self.get_deprecated(d)) is not None:
                        item.func.deprecated = (
                            f"function {item.fullname} is deprecated: {deprecated}"
                        )

    def add_function_to_symbol_table(self, func: FuncDef | OverloadedFuncDef) -> None:
        if self.is_class_scope():
            assert self.type is not None
            func.info = self.type
        func._fullname = self.qualified_name(func.name)
        self.add_symbol(func.name, func, func)

    def analyze_arg_initializers(self, defn: FuncItem) -> None:
        fullname = self.function_fullname(defn.fullname)
        with self.tvar_scope_frame(self.tvar_scope.method_frame(fullname)):
            # Analyze default arguments
            for arg in defn.arguments:
                if arg.initializer:
                    arg.initializer.accept(self)

    def analyze_function_body(self, defn: FuncItem) -> None:
        is_method = self.is_class_scope()
        fullname = self.function_fullname(defn.fullname)
        with self.tvar_scope_frame(self.tvar_scope.method_frame(fullname)):
            # Bind the type variables again to visit the body.
            if defn.type:
                a = self.type_analyzer()
                typ = defn.type
                assert isinstance(typ, CallableType)
                a.bind_function_type_variables(typ, defn)
                for i in range(len(typ.arg_types)):
                    store_argument_type(defn, i, typ, self.named_type)
            self.function_stack.append(defn)
            with self.enter(defn):
                for arg in defn.arguments:
                    self.add_local(arg.variable, defn)

                # The first argument of a non-static, non-class method is like 'self'
                # (though the name could be different), having the enclosing class's
                # instance type.
                if is_method and (not defn.is_static or defn.name == "__new__") and defn.arguments:
                    if not defn.is_class:
                        defn.arguments[0].variable.is_self = True
                    else:
                        defn.arguments[0].variable.is_cls = True

                defn.body.accept(self)
            self.function_stack.pop()

    def check_classvar_in_signature(self, typ: ProperType) -> None:
        t: ProperType
        if isinstance(typ, Overloaded):
            for t in typ.items:
                self.check_classvar_in_signature(t)
            return
        if not isinstance(typ, CallableType):
            return
        for t in get_proper_types(typ.arg_types) + [get_proper_type(typ.ret_type)]:
            if self.is_classvar(t):
                self.fail_invalid_classvar(t)
                # Show only one error per signature
                break

    def check_function_signature(self, fdef: FuncItem) -> None:
        sig = fdef.type
        assert isinstance(sig, CallableType)
        if len(sig.arg_types) < len(fdef.arguments):
            self.fail("Type signature has too few arguments", fdef)
            # Add dummy Any arguments to prevent crashes later.
            num_extra_anys = len(fdef.arguments) - len(sig.arg_types)
            extra_anys = [AnyType(TypeOfAny.from_error)] * num_extra_anys
            sig.arg_types.extend(extra_anys)
        elif len(sig.arg_types) > len(fdef.arguments):
            self.fail("Type signature has too many arguments", fdef, blocker=True)

    def visit_decorator(self, dec: Decorator) -> None:
        self.statement = dec
        # TODO: better don't modify them at all.
        dec.decorators = dec.original_decorators.copy()
        dec.func.is_conditional = self.block_depth[-1] > 0
        if not dec.is_overload:
            self.add_symbol(dec.name, dec, dec)
        dec.func._fullname = self.qualified_name(dec.name)
        dec.var._fullname = self.qualified_name(dec.name)
        for d in dec.decorators:
            d.accept(self)
        removed: list[int] = []
        no_type_check = False
        could_be_decorated_property = False
        for i, d in enumerate(dec.decorators):
            # A bunch of decorators are special cased here.
            if refers_to_fullname(d, "abc.abstractmethod"):
                removed.append(i)
                dec.func.abstract_status = IS_ABSTRACT
                self.check_decorated_function_is_method("abstractmethod", dec)
            elif refers_to_fullname(d, ("asyncio.coroutines.coroutine", "types.coroutine")):
                removed.append(i)
                dec.func.is_awaitable_coroutine = True
            elif refers_to_fullname(d, "builtins.staticmethod"):
                removed.append(i)
                dec.func.is_static = True
                dec.var.is_staticmethod = True
                self.check_decorated_function_is_method("staticmethod", dec)
            elif refers_to_fullname(d, "builtins.classmethod"):
                removed.append(i)
                dec.func.is_class = True
                dec.var.is_classmethod = True
                self.check_decorated_function_is_method("classmethod", dec)
            elif refers_to_fullname(d, OVERRIDE_DECORATOR_NAMES):
                removed.append(i)
                dec.func.is_explicit_override = True
                self.check_decorated_function_is_method("override", dec)
            elif refers_to_fullname(
                d,
                (
                    "builtins.property",
                    "abc.abstractproperty",
                    "functools.cached_property",
                    "enum.property",
                    "types.DynamicClassAttribute",
                ),
            ):
                removed.append(i)
                dec.func.is_property = True
                dec.var.is_property = True
                if refers_to_fullname(d, "abc.abstractproperty"):
                    dec.func.abstract_status = IS_ABSTRACT
                elif refers_to_fullname(d, "functools.cached_property"):
                    dec.var.is_settable_property = True
                self.check_decorated_function_is_method("property", dec)
            elif refers_to_fullname(d, "typing.no_type_check"):
                dec.var.type = AnyType(TypeOfAny.special_form)
                no_type_check = True
            elif refers_to_fullname(d, FINAL_DECORATOR_NAMES):
                if self.is_class_scope():
                    assert self.type is not None, "No type set at class scope"
                    if self.type.is_protocol:
                        self.msg.protocol_members_cant_be_final(d)
                    else:
                        dec.func.is_final = True
                        dec.var.is_final = True
                    removed.append(i)
                else:
                    self.fail("@final cannot be used with non-method functions", d)
            elif refers_to_fullname(d, TYPE_CHECK_ONLY_NAMES):
                # TODO: support `@overload` funcs.
                dec.func.is_type_check_only = True
            elif isinstance(d, CallExpr) and refers_to_fullname(
                d.callee, DATACLASS_TRANSFORM_NAMES
            ):
                dec.func.dataclass_transform_spec = self.parse_dataclass_transform_spec(d)
            elif (deprecated := self.get_deprecated(d)) is not None:
                dec.func.deprecated = f"function {dec.fullname} is deprecated: {deprecated}"
            elif not dec.var.is_property:
                # We have seen a "non-trivial" decorator before seeing @property, if
                # we will see a @property later, give an error, as we don't support this.
                could_be_decorated_property = True
        for i in reversed(removed):
            del dec.decorators[i]
        if (not dec.is_overload or dec.var.is_property) and self.type:
            dec.var.info = self.type
            dec.var.is_initialized_in_class = True
        if not no_type_check and self.recurse_into_functions:
            dec.func.accept(self)
        if could_be_decorated_property and dec.decorators and dec.var.is_property:
            self.fail(
                "Decorators on top of @property are not supported", dec, code=PROPERTY_DECORATOR
            )
        if (dec.func.is_static or dec.func.is_class) and dec.var.is_property:
            self.fail("Only instance methods can be decorated with @property", dec)
        if dec.func.abstract_status == IS_ABSTRACT and dec.func.is_final:
            self.fail(f"Method {dec.func.name} is both abstract and final", dec)
        if dec.func.is_static and dec.func.is_class:
            self.fail(message_registry.CLASS_PATTERN_CLASS_OR_STATIC_METHOD, dec)

    def check_decorated_function_is_method(self, decorator: str, context: Context) -> None:
        if not self.type or self.is_func_scope():
            self.fail(f'"{decorator}" used with a non-method', context)

    #
    # Classes
    #

    def visit_class_def(self, defn: ClassDef) -> None:
        self.statement = defn
        self.incomplete_type_stack.append(not defn.info)
        namespace = self.qualified_name(defn.name)
        with self.tvar_scope_frame(self.tvar_scope.class_frame(namespace)):
            if self.push_type_args(defn.type_args, defn) is None:
                self.mark_incomplete(defn.name, defn)
                return

            self.analyze_class(defn)
            self.pop_type_args(defn.type_args)
        self.incomplete_type_stack.pop()

    def push_type_args(
        self, type_args: list[TypeParam] | None, context: Context
    ) -> list[tuple[str, TypeVarLikeExpr]] | None:
        if not type_args:
            return []
        self.locals.append(SymbolTable())
        self.scope_stack.append(SCOPE_ANNOTATION)
        tvs: list[tuple[str, TypeVarLikeExpr]] = []
        for p in type_args:
            tv = self.analyze_type_param(p, context)
            if tv is None:
                return None
            tvs.append((p.name, tv))

        for name, tv in tvs:
            if self.is_defined_type_param(name):
                self.fail(f'"{name}" already defined as a type parameter', context)
            else:
                self.add_symbol(name, tv, context, no_progress=True, type_param=True)

        return tvs

    def is_defined_type_param(self, name: str) -> bool:
        for names in self.locals:
            if names is None:
                continue
            if name in names:
                node = names[name].node
                if isinstance(node, TypeVarLikeExpr):
                    return True
        return False

    def analyze_type_param(
        self, type_param: TypeParam, context: Context
    ) -> TypeVarLikeExpr | None:
        fullname = self.qualified_name(type_param.name)
        if type_param.upper_bound:
            upper_bound = self.anal_type(type_param.upper_bound, allow_placeholder=True)
            # TODO: we should validate the upper bound is valid for a given kind.
            if upper_bound is None:
                # This and below copies special-casing for old-style type variables, that
                # is equally necessary for new-style classes to break a vicious circle.
                upper_bound = PlaceholderType(None, [], context.line)
        else:
            if type_param.kind == TYPE_VAR_TUPLE_KIND:
                upper_bound = self.named_type("builtins.tuple", [self.object_type()])
            else:
                upper_bound = self.object_type()
        if type_param.default:
            default = self.anal_type(
                type_param.default,
                allow_placeholder=True,
                allow_unbound_tvars=True,
                report_invalid_types=False,
                allow_param_spec_literals=type_param.kind == PARAM_SPEC_KIND,
                allow_tuple_literal=type_param.kind == PARAM_SPEC_KIND,
                allow_unpack=type_param.kind == TYPE_VAR_TUPLE_KIND,
            )
            if default is None:
                default = PlaceholderType(None, [], context.line)
            elif type_param.kind == TYPE_VAR_KIND:
                default = self.check_typevar_default(default, type_param.default)
            elif type_param.kind == PARAM_SPEC_KIND:
                default = self.check_paramspec_default(default, type_param.default)
            elif type_param.kind == TYPE_VAR_TUPLE_KIND:
                default = self.check_typevartuple_default(default, type_param.default)
        else:
            default = AnyType(TypeOfAny.from_omitted_generics)
        if type_param.kind == TYPE_VAR_KIND:
            values: list[Type] = []
            if type_param.values:
                for value in type_param.values:
                    analyzed = self.anal_type(value, allow_placeholder=True)
                    if analyzed is None:
                        analyzed = PlaceholderType(None, [], context.line)
                    if has_type_vars(analyzed):
                        self.fail(message_registry.TYPE_VAR_GENERIC_CONSTRAINT_TYPE, context)
                        values.append(AnyType(TypeOfAny.from_error))
                    else:
                        values.append(analyzed)
            return TypeVarExpr(
                name=type_param.name,
                fullname=fullname,
                values=values,
                upper_bound=upper_bound,
                default=default,
                variance=VARIANCE_NOT_READY,
                is_new_style=True,
                line=context.line,
            )
        elif type_param.kind == PARAM_SPEC_KIND:
            return ParamSpecExpr(
                name=type_param.name,
                fullname=fullname,
                upper_bound=upper_bound,
                default=default,
                is_new_style=True,
                line=context.line,
            )
        else:
            assert type_param.kind == TYPE_VAR_TUPLE_KIND
            tuple_fallback = self.named_type("builtins.tuple", [self.object_type()])
            return TypeVarTupleExpr(
                name=type_param.name,
                fullname=fullname,
                upper_bound=upper_bound,
                tuple_fallback=tuple_fallback,
                default=default,
                is_new_style=True,
                line=context.line,
            )

    def pop_type_args(self, type_args: list[TypeParam] | None) -> None:
        if not type_args:
            return
        self.locals.pop()
        self.scope_stack.pop()

    def analyze_class(self, defn: ClassDef) -> None:
        fullname = self.qualified_name(defn.name)
        if not defn.info and not self.is_core_builtin_class(defn):
            # Add placeholder so that self-references in base classes can be
            # resolved.  We don't want this to cause a deferral, since if there
            # are no incomplete references, we'll replace this with a TypeInfo
            # before returning.
            placeholder = PlaceholderNode(fullname, defn, defn.line, becomes_typeinfo=True)
            self.add_symbol(defn.name, placeholder, defn, can_defer=False)

        tag = self.track_incomplete_refs()

        # Restore base classes after previous iteration (things like Generic[T] might be removed).
        defn.base_type_exprs.extend(defn.removed_base_type_exprs)
        defn.removed_base_type_exprs.clear()

        self.infer_metaclass_and_bases_from_compat_helpers(defn)

        bases = defn.base_type_exprs
        bases, tvar_defs, is_protocol = self.clean_up_bases_and_infer_type_variables(
            defn, bases, context=defn
        )

        self.check_type_alias_bases(bases)

        for tvd in tvar_defs:
            if isinstance(tvd, TypeVarType) and any(
                has_placeholder(t) for t in [tvd.upper_bound] + tvd.values
            ):
                # Some type variable bounds or values are not ready, we need
                # to re-analyze this class.
                self.defer()
            if has_placeholder(tvd.default):
                # Placeholder values in TypeVarLikeTypes may get substituted in.
                # Defer current target until they are ready.
                self.mark_incomplete(defn.name, defn)
                return

        self.analyze_class_keywords(defn)
        bases_result = self.analyze_base_classes(bases)
        if bases_result is None or self.found_incomplete_ref(tag):
            # Something was incomplete. Defer current target.
            self.mark_incomplete(defn.name, defn)
            return

        base_types, base_error = bases_result
        if any(isinstance(base, PlaceholderType) for base, _ in base_types):
            # We need to know the TypeInfo of each base to construct the MRO. Placeholder types
            # are okay in nested positions, since they can't affect the MRO.
            self.mark_incomplete(defn.name, defn)
            return

        declared_metaclass, should_defer, any_meta = self.get_declared_metaclass(
            defn.name, defn.metaclass
        )
        if should_defer or self.found_incomplete_ref(tag):
            # Metaclass was not ready. Defer current target.
            self.mark_incomplete(defn.name, defn)
            return

        if self.analyze_typeddict_classdef(defn):
            if defn.info:
                self.setup_type_vars(defn, tvar_defs)
                self.setup_alias_type_vars(defn)
            return

        if self.analyze_namedtuple_classdef(defn, tvar_defs):
            return

        # Create TypeInfo for class now that base classes and the MRO can be calculated.
        self.prepare_class_def(defn)
        self.setup_type_vars(defn, tvar_defs)
        if base_error:
            defn.info.fallback_to_any = True
        if any_meta:
            defn.info.meta_fallback_to_any = True

        with self.scope.class_scope(defn.info):
            self.configure_base_classes(defn, base_types)
            defn.info.is_protocol = is_protocol
            self.recalculate_metaclass(defn, declared_metaclass)
            defn.info.runtime_protocol = False

            if defn.type_args:
                # PEP 695 type parameters are not in scope in class decorators, so
                # temporarily disable type parameter namespace.
                type_params_names = self.locals.pop()
                self.scope_stack.pop()
            for decorator in defn.decorators:
                self.analyze_class_decorator(defn, decorator)
            if defn.type_args:
                self.locals.append(type_params_names)
                self.scope_stack.append(SCOPE_ANNOTATION)

            self.analyze_class_body_common(defn)

    def check_type_alias_bases(self, bases: list[Expression]) -> None:
        for base in bases:
            if isinstance(base, IndexExpr):
                base = base.base
            if (
                isinstance(base, RefExpr)
                and isinstance(base.node, TypeAlias)
                and base.node.python_3_12_type_alias
            ):
                self.fail(
                    'Type alias defined using "type" statement not valid as base class', base
                )

    def setup_type_vars(self, defn: ClassDef, tvar_defs: list[TypeVarLikeType]) -> None:
        defn.type_vars = tvar_defs
        defn.info.type_vars = []
        # we want to make sure any additional logic in add_type_vars gets run
        defn.info.add_type_vars()

    def setup_alias_type_vars(self, defn: ClassDef) -> None:
        assert defn.info.special_alias is not None
        defn.info.special_alias.alias_tvars = list(defn.type_vars)
        # It is a bit unfortunate that we need to inline some logic from TypeAlias constructor,
        # but it is required, since type variables may change during semantic analyzer passes.
        for i, t in enumerate(defn.type_vars):
            if isinstance(t, TypeVarTupleType):
                defn.info.special_alias.tvar_tuple_index = i
        target = defn.info.special_alias.target
        assert isinstance(target, ProperType)
        if isinstance(target, TypedDictType):
            target.fallback.args = type_vars_as_args(defn.type_vars)
        elif isinstance(target, TupleType):
            target.partial_fallback.args = type_vars_as_args(defn.type_vars)
        else:
            assert False, f"Unexpected special alias type: {type(target)}"

    def is_core_builtin_class(self, defn: ClassDef) -> bool:
        return self.cur_mod_id == "builtins" and defn.name in CORE_BUILTIN_CLASSES

    def analyze_class_body_common(self, defn: ClassDef) -> None:
        """Parts of class body analysis that are common to all kinds of class defs."""
        self.enter_class(defn.info)
        if any(b.self_type is not None for b in defn.info.mro):
            self.setup_self_type()
        defn.defs.accept(self)
        self.apply_class_plugin_hooks(defn)
        self.leave_class()

    def analyze_typeddict_classdef(self, defn: ClassDef) -> bool:
        if (
            defn.info
            and defn.info.typeddict_type
            and not has_placeholder(defn.info.typeddict_type)
        ):
            # This is a valid TypedDict, and it is fully analyzed.
            return True
        is_typeddict, info = self.typed_dict_analyzer.analyze_typeddict_classdef(defn)
        if is_typeddict:
            for decorator in defn.decorators:
                decorator.accept(self)
                if info is not None:
                    self.analyze_class_decorator_common(defn, info, decorator)
            if info is None:
                self.mark_incomplete(defn.name, defn)
            else:
                self.prepare_class_def(defn, info, custom_names=True)
            return True
        return False

    def analyze_namedtuple_classdef(
        self, defn: ClassDef, tvar_defs: list[TypeVarLikeType]
    ) -> bool:
        """Check if this class can define a named tuple."""
        if (
            defn.info
            and defn.info.is_named_tuple
            and defn.info.tuple_type
            and not has_placeholder(defn.info.tuple_type)
        ):
            # Don't reprocess everything. We just need to process methods defined
            # in the named tuple class body.
            is_named_tuple = True
            info: TypeInfo | None = defn.info
        else:
            is_named_tuple, info = self.named_tuple_analyzer.analyze_namedtuple_classdef(
                defn, self.is_stub_file, self.is_func_scope()
            )
        if is_named_tuple:
            if info is None:
                self.mark_incomplete(defn.name, defn)
            else:
                self.prepare_class_def(defn, info, custom_names=True)
                self.setup_type_vars(defn, tvar_defs)
                self.setup_alias_type_vars(defn)
                with self.scope.class_scope(defn.info):
                    for deco in defn.decorators:
                        deco.accept(self)
                        self.analyze_class_decorator_common(defn, defn.info, deco)
                    with self.named_tuple_analyzer.save_namedtuple_body(info):
                        self.analyze_class_body_common(defn)
            return True
        return False

    def apply_class_plugin_hooks(self, defn: ClassDef) -> None:
        """Apply a plugin hook that may infer a more precise definition for a class."""

        for decorator in defn.decorators:
            decorator_name = self.get_fullname_for_hook(decorator)
            if decorator_name:
                hook = self.plugin.get_class_decorator_hook(decorator_name)
                # Special case: if the decorator is itself decorated with
                # typing.dataclass_transform, apply the hook for the dataclasses plugin
                # TODO: remove special casing here
                if hook is None and find_dataclass_transform_spec(decorator):
                    hook = dataclasses_plugin.dataclass_tag_callback
                if hook:
                    hook(ClassDefContext(defn, decorator, self))

        if defn.metaclass:
            metaclass_name = self.get_fullname_for_hook(defn.metaclass)
            if metaclass_name:
                hook = self.plugin.get_metaclass_hook(metaclass_name)
                if hook:
                    hook(ClassDefContext(defn, defn.metaclass, self))

        for base_expr in defn.base_type_exprs:
            base_name = self.get_fullname_for_hook(base_expr)
            if base_name:
                hook = self.plugin.get_base_class_hook(base_name)
                if hook:
                    hook(ClassDefContext(defn, base_expr, self))

        # Check if the class definition itself triggers a dataclass transform (via a parent class/
        # metaclass)
        spec = find_dataclass_transform_spec(defn)
        if spec is not None:
            dataclasses_plugin.add_dataclass_tag(defn.info)

    def get_fullname_for_hook(self, expr: Expression) -> str | None:
        if isinstance(expr, CallExpr):
            return self.get_fullname_for_hook(expr.callee)
        elif isinstance(expr, IndexExpr):
            return self.get_fullname_for_hook(expr.base)
        elif isinstance(expr, RefExpr):
            if expr.fullname:
                return expr.fullname
            # If we don't have a fullname look it up. This happens because base classes are
            # analyzed in a different manner (see exprtotype.py) and therefore those AST
            # nodes will not have full names.
            sym = self.lookup_type_node(expr)
            if sym:
                return sym.fullname
        return None

    def analyze_class_keywords(self, defn: ClassDef) -> None:
        for value in defn.keywords.values():
            value.accept(self)

    def enter_class(self, info: TypeInfo) -> None:
        # Remember previous active class
        self.type_stack.append(self.type)
        self.locals.append(None)  # Add class scope
        self.scope_stack.append(SCOPE_CLASS)
        self.block_depth.append(-1)  # The class body increments this to 0
        self.loop_depth.append(0)
        self._type = info
        self.missing_names.append(set())

    def leave_class(self) -> None:
        """Restore analyzer state."""
        self.block_depth.pop()
        self.loop_depth.pop()
        self.locals.pop()
        self.scope_stack.pop()
        self._type = self.type_stack.pop()
        self.missing_names.pop()

    def analyze_class_decorator(self, defn: ClassDef, decorator: Expression) -> None:
        decorator.accept(self)
        self.analyze_class_decorator_common(defn, defn.info, decorator)
        if isinstance(decorator, RefExpr):
            if decorator.fullname in RUNTIME_PROTOCOL_DECOS:
                if defn.info.is_protocol:
                    defn.info.runtime_protocol = True
                else:
                    self.fail("@runtime_checkable can only be used with protocol classes", defn)
        elif isinstance(decorator, CallExpr) and refers_to_fullname(
            decorator.callee, DATACLASS_TRANSFORM_NAMES
        ):
            defn.info.dataclass_transform_spec = self.parse_dataclass_transform_spec(decorator)

    def analyze_class_decorator_common(
        self, defn: ClassDef, info: TypeInfo, decorator: Expression
    ) -> None:
        """Common method for applying class decorators.

        Called on regular classes, typeddicts, and namedtuples.
        """
        if refers_to_fullname(decorator, FINAL_DECORATOR_NAMES):
            info.is_final = True
        elif refers_to_fullname(decorator, TYPE_CHECK_ONLY_NAMES):
            info.is_type_check_only = True
        elif (deprecated := self.get_deprecated(decorator)) is not None:
            info.deprecated = f"class {defn.fullname} is deprecated: {deprecated}"

    def clean_up_bases_and_infer_type_variables(
        self, defn: ClassDef, base_type_exprs: list[Expression], context: Context
    ) -> tuple[list[Expression], list[TypeVarLikeType], bool]:
        """Remove extra base classes such as Generic and infer type vars.

        For example, consider this class:

          class Foo(Bar, Generic[T]): ...

        Now we will remove Generic[T] from bases of Foo and infer that the
        type variable 'T' is a type argument of Foo.

        Note that this is performed *before* semantic analysis.

        Returns (remaining base expressions, inferred type variables, is protocol).
        """
        removed: list[int] = []
        declared_tvars: TypeVarLikeList = []
        is_protocol = False
        if defn.type_args is not None:
            for p in defn.type_args:
                node = self.lookup(p.name, context)
                assert node is not None
                assert isinstance(node.node, TypeVarLikeExpr)
                declared_tvars.append((p.name, node.node))

        for i, base_expr in enumerate(base_type_exprs):
            if isinstance(base_expr, StarExpr):
                base_expr.valid = True
            self.analyze_type_expr(base_expr)

            try:
                base = self.expr_to_unanalyzed_type(base_expr)
            except TypeTranslationError:
                # This error will be caught later.
                continue
            result = self.analyze_class_typevar_declaration(base)
            if result is not None:
                tvars = result[0]
                is_protocol |= result[1]
                if declared_tvars:
                    if defn.type_args:
                        if is_protocol:
                            self.fail('No arguments expected for "Protocol" base class', context)
                        else:
                            self.fail("Generic[...] base class is redundant", context)
                    else:
                        self.fail(
                            "Only single Generic[...] or Protocol[...] can be in bases", context
                        )
                removed.append(i)
                declared_tvars.extend(tvars)
            if isinstance(base, UnboundType):
                sym = self.lookup_qualified(base.name, base)
                if sym is not None and sym.node is not None:
                    if sym.node.fullname in PROTOCOL_NAMES and i not in removed:
                        # also remove bare 'Protocol' bases
                        removed.append(i)
                        is_protocol = True

        all_tvars = self.get_all_bases_tvars(base_type_exprs, removed)
        if declared_tvars:
            if len(remove_dups(declared_tvars)) < len(declared_tvars) and not defn.type_args:
                self.fail("Duplicate type variables in Generic[...] or Protocol[...]", context)
            declared_tvars = remove_dups(declared_tvars)
            if not set(all_tvars).issubset(set(declared_tvars)):
                if defn.type_args:
                    undeclared = sorted(set(all_tvars) - set(declared_tvars))
                    self.msg.type_parameters_should_be_declared(
                        [tv[0] for tv in undeclared], context
                    )
                else:
                    self.fail(
                        "If Generic[...] or Protocol[...] is present"
                        " it should list all type variables",
                        context,
                    )
                # In case of error, Generic tvars will go first
                declared_tvars = remove_dups(declared_tvars + all_tvars)
        else:
            declared_tvars = all_tvars
        for i in reversed(removed):
            # We need to actually remove the base class expressions like Generic[T],
            # mostly because otherwise they will create spurious dependencies in fine
            # grained incremental mode.
            defn.removed_base_type_exprs.append(defn.base_type_exprs[i])
            del base_type_exprs[i]
        tvar_defs = self.tvar_defs_from_tvars(declared_tvars, context)
        return base_type_exprs, tvar_defs, is_protocol

    def analyze_class_typevar_declaration(self, base: Type) -> tuple[TypeVarLikeList, bool] | None:
        """Analyze type variables declared using Generic[...] or Protocol[...].

        Args:
            base: Non-analyzed base class

        Return None if the base class does not declare type variables. Otherwise,
        return the type variables.
        """
        if not isinstance(base, UnboundType):
            return None
        unbound = base
        sym = self.lookup_qualified(unbound.name, unbound)
        if sym is None or sym.node is None:
            return None
        if (
            sym.node.fullname == "typing.Generic"
            or sym.node.fullname in PROTOCOL_NAMES
            and base.args
        ):
            is_proto = sym.node.fullname != "typing.Generic"
            tvars: TypeVarLikeList = []
            have_type_var_tuple = False
            for arg in unbound.args:
                tag = self.track_incomplete_refs()
                tvar = self.analyze_unbound_tvar(arg)
                if tvar:
                    if isinstance(tvar[1], TypeVarTupleExpr):
                        if have_type_var_tuple:
                            self.fail("Can only use one type var tuple in a class def", base)
                            continue
                        have_type_var_tuple = True
                    tvars.append(tvar)
                elif not self.found_incomplete_ref(tag):
                    self.fail("Free type variable expected in %s[...]" % sym.node.name, base)
            return tvars, is_proto
        return None

    def analyze_unbound_tvar(self, t: Type) -> tuple[str, TypeVarLikeExpr] | None:
        if isinstance(t, UnpackType) and isinstance(t.type, UnboundType):
            return self.analyze_unbound_tvar_impl(t.type, is_unpacked=True)
        if isinstance(t, UnboundType):
            sym = self.lookup_qualified(t.name, t)
            if sym and sym.fullname in UNPACK_TYPE_NAMES:
                inner_t = t.args[0]
                if isinstance(inner_t, UnboundType):
                    return self.analyze_unbound_tvar_impl(inner_t, is_unpacked=True)
                return None
            return self.analyze_unbound_tvar_impl(t)
        return None

    def analyze_unbound_tvar_impl(
        self, t: UnboundType, is_unpacked: bool = False, is_typealias_param: bool = False
    ) -> tuple[str, TypeVarLikeExpr] | None:
        assert not is_unpacked or not is_typealias_param, "Mutually exclusive conditions"
        sym = self.lookup_qualified(t.name, t)
        if sym and isinstance(sym.node, PlaceholderNode):
            self.record_incomplete_ref()
        if not is_unpacked and sym and isinstance(sym.node, ParamSpecExpr):
            if sym.fullname and not self.tvar_scope.allow_binding(sym.fullname):
                # It's bound by our type variable scope
                return None
            return t.name, sym.node
        if (is_unpacked or is_typealias_param) and sym and isinstance(sym.node, TypeVarTupleExpr):
            if sym.fullname and not self.tvar_scope.allow_binding(sym.fullname):
                # It's bound by our type variable scope
                return None
            return t.name, sym.node
        if sym is None or not isinstance(sym.node, TypeVarExpr) or is_unpacked:
            return None
        elif sym.fullname and not self.tvar_scope.allow_binding(sym.fullname):
            # It's bound by our type variable scope
            return None
        else:
            assert isinstance(sym.node, TypeVarExpr)
            return t.name, sym.node

    def find_type_var_likes(self, t: Type) -> TypeVarLikeList:
        visitor = FindTypeVarVisitor(self, self.tvar_scope)
        t.accept(visitor)
        return visitor.type_var_likes

    def get_all_bases_tvars(
        self, base_type_exprs: list[Expression], removed: list[int]
    ) -> TypeVarLikeList:
        """Return all type variable references in bases."""
        tvars: TypeVarLikeList = []
        for i, base_expr in enumerate(base_type_exprs):
            if i not in removed:
                try:
                    base = self.expr_to_unanalyzed_type(base_expr)
                except TypeTranslationError:
                    # This error will be caught later.
                    continue
                base_tvars = self.find_type_var_likes(base)
                tvars.extend(base_tvars)
        return remove_dups(tvars)

    def tvar_defs_from_tvars(
        self, tvars: TypeVarLikeList, context: Context
    ) -> list[TypeVarLikeType]:
        tvar_defs: list[TypeVarLikeType] = []
        last_tvar_name_with_default: str | None = None
        for name, tvar_expr in tvars:
            tvar_expr.default = tvar_expr.default.accept(
                TypeVarDefaultTranslator(self, tvar_expr.name, context)
            )
            tvar_def = self.tvar_scope.bind_new(name, tvar_expr)
            if last_tvar_name_with_default is not None and not tvar_def.has_default():
                self.msg.tvar_without_default_type(
                    tvar_def.name, last_tvar_name_with_default, context
                )
                tvar_def.default = AnyType(TypeOfAny.from_error)
            elif tvar_def.has_default():
                last_tvar_name_with_default = tvar_def.name
            tvar_defs.append(tvar_def)
        return tvar_defs

    def get_and_bind_all_tvars(self, type_exprs: list[Expression]) -> list[TypeVarLikeType]:
        """Return all type variable references in item type expressions.

        This is a helper for generic TypedDicts and NamedTuples. Essentially it is
        a simplified version of the logic we use for ClassDef bases. We duplicate
        some amount of code, because it is hard to refactor common pieces.
        """
        tvars = []
        for base_expr in type_exprs:
            try:
                base = self.expr_to_unanalyzed_type(base_expr)
            except TypeTranslationError:
                # This error will be caught later.
                continue
            base_tvars = self.find_type_var_likes(base)
            tvars.extend(base_tvars)
        tvars = remove_dups(tvars)  # Variables are defined in order of textual appearance.
        tvar_defs = []
        for name, tvar_expr in tvars:
            tvar_def = self.tvar_scope.bind_new(name, tvar_expr)
            tvar_defs.append(tvar_def)
        return tvar_defs

    def prepare_class_def(
        self, defn: ClassDef, info: TypeInfo | None = None, custom_names: bool = False
    ) -> None:
        """Prepare for the analysis of a class definition.

        Create an empty TypeInfo and store it in a symbol table, or if the 'info'
        argument is provided, store it instead (used for magic type definitions).
        """
        if not defn.info:
            defn.fullname = self.qualified_name(defn.name)
            # TODO: Nested classes
            info = info or self.make_empty_type_info(defn)
            defn.info = info
            info.defn = defn
            if not custom_names:
                # Some special classes (in particular NamedTuples) use custom fullname logic.
                # Don't override it here (also see comment below, this needs cleanup).
                if not self.is_func_scope():
                    info._fullname = self.qualified_name(defn.name)
                else:
                    info._fullname = info.name
        local_name = defn.name
        if "@" in local_name:
            local_name = local_name.split("@")[0]
        self.add_symbol(local_name, defn.info, defn)
        if self.is_nested_within_func_scope():
            # We need to preserve local classes, let's store them
            # in globals under mangled unique names
            #
            # TODO: Putting local classes into globals breaks assumptions in fine-grained
            #       incremental mode and we should avoid it. In general, this logic is too
            #       ad-hoc and needs to be removed/refactored.
            if "@" not in defn.info._fullname:
                global_name = defn.info.name + "@" + str(defn.line)
                defn.info._fullname = self.cur_mod_id + "." + global_name
            else:
                # Preserve name from previous fine-grained incremental run.
                global_name = defn.info.name
            defn.fullname = defn.info._fullname
            if defn.info.is_named_tuple or defn.info.typeddict_type:
                # Named tuples and Typed dicts nested within a class are stored
                # in the class symbol table.
                self.add_symbol_skip_local(global_name, defn.info)
            else:
                self.globals[global_name] = SymbolTableNode(GDEF, defn.info)

    def make_empty_type_info(self, defn: ClassDef) -> TypeInfo:
        if (
            self.is_module_scope()
            and self.cur_mod_id == "builtins"
            and defn.name in CORE_BUILTIN_CLASSES
        ):
            # Special case core built-in classes. A TypeInfo was already
            # created for it before semantic analysis, but with a dummy
            # ClassDef. Patch the real ClassDef object.
            info = self.globals[defn.name].node
            assert isinstance(info, TypeInfo)
        else:
            info = TypeInfo(SymbolTable(), defn, self.cur_mod_id)
            info.set_line(defn)
        return info

    def get_name_repr_of_expr(self, expr: Expression) -> str | None:
        """Try finding a short simplified textual representation of a base class expression."""
        if isinstance(expr, NameExpr):
            return expr.name
        if isinstance(expr, MemberExpr):
            return get_member_expr_fullname(expr)
        if isinstance(expr, IndexExpr):
            return self.get_name_repr_of_expr(expr.base)
        if isinstance(expr, CallExpr):
            return self.get_name_repr_of_expr(expr.callee)
        return None

    def analyze_base_classes(
        self, base_type_exprs: list[Expression]
    ) -> tuple[list[tuple[ProperType, Expression]], bool] | None:
        """Analyze base class types.

        Return None if some definition was incomplete. Otherwise, return a tuple
        with these items:

         * List of (analyzed type, original expression) tuples
         * Boolean indicating whether one of the bases had a semantic analysis error
        """
        is_error = False
        bases = []
        for base_expr in base_type_exprs:
            if (
                isinstance(base_expr, RefExpr)
                and base_expr.fullname in TYPED_NAMEDTUPLE_NAMES + TPDICT_NAMES
            ) or (
                isinstance(base_expr, CallExpr)
                and isinstance(base_expr.callee, RefExpr)
                and base_expr.callee.fullname in TPDICT_NAMES
            ):
                # Ignore magic bases for now.
                # For example:
                #  class Foo(TypedDict): ...  # RefExpr
                #  class Foo(NamedTuple): ...  # RefExpr
                #  class Foo(TypedDict("Foo", {"a": int})): ...  # CallExpr
                continue

            try:
                base = self.expr_to_analyzed_type(
                    base_expr, allow_placeholder=True, allow_type_any=True
                )
            except TypeTranslationError:
                name = self.get_name_repr_of_expr(base_expr)
                if isinstance(base_expr, CallExpr):
                    msg = "Unsupported dynamic base class"
                else:
                    msg = "Invalid base class"
                if name:
                    msg += f' "{name}"'
                self.fail(msg, base_expr)
                is_error = True
                continue
            if base is None:
                return None
            base = get_proper_type(base)
            bases.append((base, base_expr))
        return bases, is_error

    def configure_base_classes(
        self, defn: ClassDef, bases: list[tuple[ProperType, Expression]]
    ) -> None:
        """Set up base classes.

        This computes several attributes on the corresponding TypeInfo defn.info
        related to the base classes: defn.info.bases, defn.info.mro, and
        miscellaneous others (at least tuple_type, fallback_to_any, and is_enum.)
        """
        base_types: list[Instance] = []
        info = defn.info

        for base, base_expr in bases:
            if isinstance(base, TupleType):
                actual_base = self.configure_tuple_base_class(defn, base)
                base_types.append(actual_base)
            elif isinstance(base, Instance):
                if base.type.is_newtype:
                    self.fail('Cannot subclass "NewType"', defn)
                base_types.append(base)
            elif isinstance(base, AnyType):
                if self.options.disallow_subclassing_any:
                    if isinstance(base_expr, (NameExpr, MemberExpr)):
                        msg = f'Class cannot subclass "{base_expr.name}" (has type "Any")'
                    else:
                        msg = 'Class cannot subclass value of type "Any"'
                    self.fail(msg, base_expr)
                info.fallback_to_any = True
            elif isinstance(base, TypedDictType):
                base_types.append(base.fallback)
            else:
                msg = "Invalid base class"
                name = self.get_name_repr_of_expr(base_expr)
                if name:
                    msg += f' "{name}"'
                self.fail(msg, base_expr)
                info.fallback_to_any = True
            if self.options.disallow_any_unimported and has_any_from_unimported_type(base):
                if isinstance(base_expr, (NameExpr, MemberExpr)):
                    prefix = f"Base type {base_expr.name}"
                else:
                    prefix = "Base type"
                self.msg.unimported_type_becomes_any(prefix, base, base_expr)
            check_for_explicit_any(
                base, self.options, self.is_typeshed_stub_file, self.msg, context=base_expr
            )

        # Add 'object' as implicit base if there is no other base class.
        if not base_types and defn.fullname != "builtins.object":
            base_types.append(self.object_type())

        info.bases = base_types

        # Calculate the MRO.
        if not self.verify_base_classes(defn):
            self.set_dummy_mro(defn.info)
            return
        if not self.verify_duplicate_base_classes(defn):
            # We don't want to block the typechecking process,
            # so, we just insert `Any` as the base class and show an error.
            self.set_any_mro(defn.info)
        self.calculate_class_mro(defn, self.object_type)

    def configure_tuple_base_class(self, defn: ClassDef, base: TupleType) -> Instance:
        info = defn.info

        # There may be an existing valid tuple type from previous semanal iterations.
        # Use equality to check if it is the case.
        if info.tuple_type and info.tuple_type != base and not has_placeholder(info.tuple_type):
            self.fail("Class has two incompatible bases derived from tuple", defn)
            defn.has_incompatible_baseclass = True
        if info.special_alias and has_placeholder(info.special_alias.target):
            self.process_placeholder(
                None, "tuple base", defn, force_progress=base != info.tuple_type
            )
        info.update_tuple_type(base)
        self.setup_alias_type_vars(defn)

        if base.partial_fallback.type.fullname == "builtins.tuple" and not has_placeholder(base):
            # Fallback can only be safely calculated after semantic analysis, since base
            # classes may be incomplete. Postpone the calculation.
            self.schedule_patch(PRIORITY_FALLBACKS, lambda: calculate_tuple_fallback(base))

        return base.partial_fallback

    def set_dummy_mro(self, info: TypeInfo) -> None:
        # Give it an MRO consisting of just the class itself and object.
        info.mro = [info, self.object_type().type]
        info.bad_mro = True

    def set_any_mro(self, info: TypeInfo) -> None:
        # Give it an MRO consisting direct `Any` subclass.
        info.fallback_to_any = True
        info.mro = [info, self.object_type().type]

    def calculate_class_mro(
        self, defn: ClassDef, obj_type: Callable[[], Instance] | None = None
    ) -> None:
        """Calculate method resolution order for a class.

        `obj_type` exists just to fill in empty base class list in case of an error.
        """
        try:
            calculate_mro(defn.info, obj_type)
        except MroError:
            self.fail(
                f'Cannot determine consistent method resolution order (MRO) for "{defn.name}"',
                defn,
            )
            self.set_dummy_mro(defn.info)
        # Allow plugins to alter the MRO to handle the fact that `def mro()`
        # on metaclasses permits MRO rewriting.
        if defn.fullname:
            hook = self.plugin.get_customize_class_mro_hook(defn.fullname)
            if hook:
                hook(ClassDefContext(defn, FakeExpression(), self))

    def infer_metaclass_and_bases_from_compat_helpers(self, defn: ClassDef) -> None:
        """Lookup for special metaclass declarations, and update defn fields accordingly.

        * six.with_metaclass(M, B1, B2, ...)
        * @six.add_metaclass(M)
        * future.utils.with_metaclass(M, B1, B2, ...)
        * past.utils.with_metaclass(M, B1, B2, ...)
        """

        # Look for six.with_metaclass(M, B1, B2, ...)
        with_meta_expr: Expression | None = None
        if len(defn.base_type_exprs) == 1:
            base_expr = defn.base_type_exprs[0]
            if isinstance(base_expr, CallExpr) and isinstance(base_expr.callee, RefExpr):
                self.analyze_type_expr(base_expr)
                if (
                    base_expr.callee.fullname
                    in {
                        "six.with_metaclass",
                        "future.utils.with_metaclass",
                        "past.utils.with_metaclass",
                    }
                    and len(base_expr.args) >= 1
                    and all(kind == ARG_POS for kind in base_expr.arg_kinds)
                ):
                    with_meta_expr = base_expr.args[0]
                    defn.base_type_exprs = base_expr.args[1:]

        # Look for @six.add_metaclass(M)
        add_meta_expr: Expression | None = None
        for dec_expr in defn.decorators:
            if isinstance(dec_expr, CallExpr) and isinstance(dec_expr.callee, RefExpr):
                dec_expr.callee.accept(self)
                if (
                    dec_expr.callee.fullname == "six.add_metaclass"
                    and len(dec_expr.args) == 1
                    and dec_expr.arg_kinds[0] == ARG_POS
                ):
                    add_meta_expr = dec_expr.args[0]
                    break

        metas = {defn.metaclass, with_meta_expr, add_meta_expr} - {None}
        if len(metas) == 0:
            return
        if len(metas) > 1:
            self.fail("Multiple metaclass definitions", defn)
            return
        defn.metaclass = metas.pop()

    def verify_base_classes(self, defn: ClassDef) -> bool:
        info = defn.info
        cycle = False
        for base in info.bases:
            baseinfo = base.type
            if self.is_base_class(info, baseinfo):
                self.fail("Cycle in inheritance hierarchy", defn)
                cycle = True
        return not cycle

    def verify_duplicate_base_classes(self, defn: ClassDef) -> bool:
        dup = find_duplicate(defn.info.direct_base_classes())
        if dup:
            self.fail(f'Duplicate base class "{dup.name}"', defn)
        return not dup

    def is_base_class(self, t: TypeInfo, s: TypeInfo) -> bool:
        """Determine if t is a base class of s (but do not use mro)."""
        # Search the base class graph for t, starting from s.
        worklist = [s]
        visited = {s}
        while worklist:
            nxt = worklist.pop()
            if nxt == t:
                return True
            for base in nxt.bases:
                if base.type not in visited:
                    worklist.append(base.type)
                    visited.add(base.type)
        return False

    def get_declared_metaclass(
        self, name: str, metaclass_expr: Expression | None
    ) -> tuple[Instance | None, bool, bool]:
        """Get declared metaclass from metaclass expression.

        Returns a tuple of three values:
          * A metaclass instance or None
          * A boolean indicating whether we should defer
          * A boolean indicating whether we should set metaclass Any fallback
            (either for Any metaclass or invalid/dynamic metaclass).

        The two boolean flags can only be True if instance is None.
        """
        declared_metaclass = None
        if metaclass_expr:
            metaclass_name = None
            if isinstance(metaclass_expr, NameExpr):
                metaclass_name = metaclass_expr.name
            elif isinstance(metaclass_expr, MemberExpr):
                metaclass_name = get_member_expr_fullname(metaclass_expr)
            if metaclass_name is None:
                self.fail(f'Dynamic metaclass not supported for "{name}"', metaclass_expr)
                return None, False, True
            sym = self.lookup_qualified(metaclass_name, metaclass_expr)
            if sym is None:
                # Probably a name error - it is already handled elsewhere
                return None, False, True
            if isinstance(sym.node, Var) and isinstance(get_proper_type(sym.node.type), AnyType):
                if self.options.disallow_subclassing_any:
                    self.fail(
                        f'Class cannot use "{sym.node.name}" as a metaclass (has type "Any")',
                        metaclass_expr,
                    )
                return None, False, True
            if isinstance(sym.node, PlaceholderNode):
                return None, True, False  # defer later in the caller

            # Support type aliases, like `_Meta: TypeAlias = type`
            metaclass_info: Node | None = sym.node
            if (
                isinstance(sym.node, TypeAlias)
                and not sym.node.python_3_12_type_alias
                and not sym.node.alias_tvars
            ):
                target = get_proper_type(sym.node.target)
                if isinstance(target, Instance):
                    metaclass_info = target.type

            if not isinstance(metaclass_info, TypeInfo) or metaclass_info.tuple_type is not None:
                self.fail(f'Invalid metaclass "{metaclass_name}"', metaclass_expr)
                return None, False, False
            if not metaclass_info.is_metaclass():
                self.fail(
                    'Metaclasses not inheriting from "type" are not supported', metaclass_expr
                )
                return None, False, False
            inst = fill_typevars(metaclass_info)
            assert isinstance(inst, Instance)
            declared_metaclass = inst
        return declared_metaclass, False, False

    def recalculate_metaclass(self, defn: ClassDef, declared_metaclass: Instance | None) -> None:
        defn.info.declared_metaclass = declared_metaclass
        defn.info.metaclass_type = defn.info.calculate_metaclass_type()
        if any(info.is_protocol for info in defn.info.mro):
            if (
                not defn.info.metaclass_type
                or defn.info.metaclass_type.type.fullname == "builtins.type"
            ):
                # All protocols and their subclasses have ABCMeta metaclass by default.
                # TODO: add a metaclass conflict check if there is another metaclass.
                abc_meta = self.named_type_or_none("abc.ABCMeta", [])
                if abc_meta is not None:  # May be None in tests with incomplete lib-stub.
                    defn.info.metaclass_type = abc_meta
        if defn.info.metaclass_type and defn.info.metaclass_type.type.has_base("enum.EnumMeta"):
            defn.info.is_enum = True
            if defn.type_vars:
                self.fail("Enum class cannot be generic", defn)

    #
    # Imports
    #

    def visit_import(self, i: Import) -> None:
        self.statement = i
        for id, as_id in i.ids:
            # Modules imported in a stub file without using 'import X as X' won't get exported
            # When implicit re-exporting is disabled, we have the same behavior as stubs.
            use_implicit_reexport = not self.is_stub_file and self.options.implicit_reexport
            if as_id is not None:
                base_id = id
                imported_id = as_id
                module_public = use_implicit_reexport or id == as_id
            else:
                base_id = id.split(".")[0]
                imported_id = base_id
                module_public = use_implicit_reexport

            if base_id in self.modules:
                node = self.modules[base_id]
                if self.is_func_scope():
                    kind = LDEF
                elif self.type is not None:
                    kind = MDEF
                else:
                    kind = GDEF
                symbol = SymbolTableNode(
                    kind, node, module_public=module_public, module_hidden=not module_public
                )
                self.add_imported_symbol(
                    imported_id,
                    symbol,
                    context=i,
                    module_public=module_public,
                    module_hidden=not module_public,
                )
            else:
                self.add_unknown_imported_symbol(
                    imported_id,
                    context=i,
                    target_name=base_id,
                    module_public=module_public,
                    module_hidden=not module_public,
                )

    def visit_import_from(self, imp: ImportFrom) -> None:
        self.statement = imp
        module_id = self.correct_relative_import(imp)
        module = self.modules.get(module_id)
        for id, as_id in imp.names:
            fullname = module_id + "." + id
            self.set_future_import_flags(fullname)
            if module is None:
                node = None
            elif module_id == self.cur_mod_id and fullname in self.modules:
                # Submodule takes precedence over definition in surround package, for
                # compatibility with runtime semantics in typical use cases. This
                # could more precisely model runtime semantics by taking into account
                # the line number beyond which the local definition should take
                # precedence, but doesn't seem to be important in most use cases.
                node = SymbolTableNode(GDEF, self.modules[fullname])
            else:
                if id == as_id == "__all__" and module_id in self.export_map:
                    self.all_exports[:] = self.export_map[module_id]
                node = module.names.get(id)

            missing_submodule = False
            imported_id = as_id or id

            # Modules imported in a stub file without using 'from Y import X as X' will
            # not get exported.
            # When implicit re-exporting is disabled, we have the same behavior as stubs.
            use_implicit_reexport = not self.is_stub_file and self.options.implicit_reexport
            module_public = use_implicit_reexport or (as_id is not None and id == as_id)

            # If the module does not contain a symbol with the name 'id',
            # try checking if it's a module instead.
            if not node:
                mod = self.modules.get(fullname)
                if mod is not None:
                    kind = self.current_symbol_kind()
                    node = SymbolTableNode(kind, mod)
                elif fullname in self.missing_modules:
                    missing_submodule = True
            # If it is still not resolved, check for a module level __getattr__
            if module and not node and "__getattr__" in module.names:
                # We store the fullname of the original definition so that we can
                # detect whether two imported names refer to the same thing.
                fullname = module_id + "." + id
                gvar = self.create_getattr_var(module.names["__getattr__"], imported_id, fullname)
                if gvar:
                    self.add_symbol(
                        imported_id,
                        gvar,
                        imp,
                        module_public=module_public,
                        module_hidden=not module_public,
                    )
                    continue

            if node:
                self.process_imported_symbol(
                    node, module_id, id, imported_id, fullname, module_public, context=imp
                )
                if node.module_hidden:
                    self.report_missing_module_attribute(
                        module_id,
                        id,
                        imported_id,
                        module_public=module_public,
                        module_hidden=not module_public,
                        context=imp,
                        add_unknown_imported_symbol=False,
                    )
            elif module and not missing_submodule:
                # Target module exists but the imported name is missing or hidden.
                self.report_missing_module_attribute(
                    module_id,
                    id,
                    imported_id,
                    module_public=module_public,
                    module_hidden=not module_public,
                    context=imp,
                )
            else:
                # Import of a missing (sub)module.
                self.add_unknown_imported_symbol(
                    imported_id,
                    imp,
                    target_name=fullname,
                    module_public=module_public,
                    module_hidden=not module_public,
                )

    def process_imported_symbol(
        self,
        node: SymbolTableNode,
        module_id: str,
        id: str,
        imported_id: str,
        fullname: str,
        module_public: bool,
        context: ImportBase,
    ) -> None:
        module_hidden = not module_public and (
            # `from package import submodule` should work regardless of whether package
            # re-exports submodule, so we shouldn't hide it
            not isinstance(node.node, MypyFile)
            or fullname not in self.modules
            # but given `from somewhere import random_unrelated_module` we should hide
            # random_unrelated_module
            or not fullname.startswith(self.cur_mod_id + ".")
        )

        if isinstance(node.node, PlaceholderNode):
            if self.final_iteration:
                self.report_missing_module_attribute(
                    module_id,
                    id,
                    imported_id,
                    module_public=module_public,
                    module_hidden=module_hidden,
                    context=context,
                )
                return
            else:
                # This might become a type.
                self.mark_incomplete(
                    imported_id,
                    node.node,
                    module_public=module_public,
                    module_hidden=module_hidden,
                    becomes_typeinfo=True,
                )
        # NOTE: we take the original node even for final `Var`s. This is to support
        # a common pattern when constants are re-exported (same applies to import *).
        self.add_imported_symbol(
            imported_id, node, context, module_public=module_public, module_hidden=module_hidden
        )

    def report_missing_module_attribute(
        self,
        import_id: str,
        source_id: str,
        imported_id: str,
        module_public: bool,
        module_hidden: bool,
        context: Node,
        add_unknown_imported_symbol: bool = True,
    ) -> None:
        # Missing attribute.
        if self.is_incomplete_namespace(import_id):
            # We don't know whether the name will be there, since the namespace
            # is incomplete. Defer the current target.
            self.mark_incomplete(
                imported_id, context, module_public=module_public, module_hidden=module_hidden
            )
            return
        message = f'Module "{import_id}" has no attribute "{source_id}"'
        # Suggest alternatives, if any match is found.
        module = self.modules.get(import_id)
        if module:
            if source_id in module.names.keys() and not module.names[source_id].module_public:
                message = (
                    f'Module "{import_id}" does not explicitly export attribute "{source_id}"'
                )
            else:
                alternatives = set(module.names.keys()).difference({source_id})
                matches = best_matches(source_id, alternatives, n=3)
                if matches:
                    suggestion = f"; maybe {pretty_seq(matches, 'or')}?"
                    message += f"{suggestion}"
        self.fail(message, context, code=codes.ATTR_DEFINED)
        if add_unknown_imported_symbol:
            self.add_unknown_imported_symbol(
                imported_id,
                context,
                target_name=None,
                module_public=module_public,
                module_hidden=not module_public,
            )

        if import_id == "typing":
            # The user probably has a missing definition in a test fixture. Let's verify.
            fullname = f"builtins.{source_id.lower()}"
            if (
                self.lookup_fully_qualified_or_none(fullname) is None
                and fullname in SUGGESTED_TEST_FIXTURES
            ):
                # Yes. Generate a helpful note.
                self.msg.add_fixture_note(fullname, context)
            else:
                typing_extensions = self.modules.get("typing_extensions")
                if typing_extensions and source_id in typing_extensions.names:
                    self.msg.note(
                        f"Use `from typing_extensions import {source_id}` instead",
                        context,
                        code=codes.ATTR_DEFINED,
                    )
                    self.msg.note(
                        "See https://mypy.readthedocs.io/en/stable/runtime_troubles.html#using-new-additions-to-the-typing-module",
                        context,
                        code=codes.ATTR_DEFINED,
                    )

    def process_import_over_existing_name(
        self,
        imported_id: str,
        existing_symbol: SymbolTableNode,
        module_symbol: SymbolTableNode,
        import_node: ImportBase,
    ) -> bool:
        if existing_symbol.node is module_symbol.node:
            # We added this symbol on previous iteration.
            return False
        if existing_symbol.kind in (LDEF, GDEF, MDEF) and isinstance(
            existing_symbol.node, (Var, FuncDef, TypeInfo, Decorator, TypeAlias)
        ):
            # This is a valid import over an existing definition in the file. Construct a dummy
            # assignment that we'll use to type check the import.
            lvalue = NameExpr(imported_id)
            lvalue.kind = existing_symbol.kind
            lvalue.node = existing_symbol.node
            rvalue = NameExpr(imported_id)
            rvalue.kind = module_symbol.kind
            rvalue.node = module_symbol.node
            if isinstance(rvalue.node, TypeAlias):
                # Suppress bogus errors from the dummy assignment if rvalue is an alias.
                # Otherwise mypy may complain that alias is invalid in runtime context.
                rvalue.is_alias_rvalue = True
            assignment = AssignmentStmt([lvalue], rvalue)
            for node in assignment, lvalue, rvalue:
                node.set_line(import_node)
            import_node.assignments.append(assignment)
            return True
        return False

    def correct_relative_import(self, node: ImportFrom | ImportAll) -> str:
        import_id, ok = correct_relative_import(
            self.cur_mod_id, node.relative, node.id, self.cur_mod_node.is_package_init_file()
        )
        if not ok:
            self.fail("Relative import climbs too many namespaces", node)
        return import_id

    def visit_import_all(self, i: ImportAll) -> None:
        i_id = self.correct_relative_import(i)
        if i_id in self.modules:
            m = self.modules[i_id]
            if self.is_incomplete_namespace(i_id):
                # Any names could be missing from the current namespace if the target module
                # namespace is incomplete.
                self.mark_incomplete("*", i)
            for name, node in m.names.items():
                fullname = i_id + "." + name
                self.set_future_import_flags(fullname)
                # if '__all__' exists, all nodes not included have had module_public set to
                # False, and we can skip checking '_' because it's been explicitly included.
                if node.module_public and (not name.startswith("_") or "__all__" in m.names):
                    if isinstance(node.node, MypyFile):
                        # Star import of submodule from a package, add it as a dependency.
                        self.imports.add(node.node.fullname)
                    # `from x import *` always reexports symbols
                    self.add_imported_symbol(
                        name, node, context=i, module_public=True, module_hidden=False
                    )

        else:
            # Don't add any dummy symbols for 'from x import *' if 'x' is unknown.
            pass

    #
    # Assignment
    #

    def visit_assignment_expr(self, s: AssignmentExpr) -> None:
        s.value.accept(self)
        if self.is_func_scope():
            if not self.check_valid_comprehension(s):
                return
        self.analyze_lvalue(s.target, escape_comprehensions=True, has_explicit_value=True)

    def check_valid_comprehension(self, s: AssignmentExpr) -> bool:
        """Check that assignment expression is not nested within comprehension at class scope.

        class C:
            [(j := i) for i in [1, 2, 3]]
        is a syntax error that is not enforced by Python parser, but at later steps.
        """
        for i, scope_type in enumerate(reversed(self.scope_stack)):
            if scope_type != SCOPE_COMPREHENSION and i < len(self.locals) - 1:
                if self.locals[-1 - i] is None:
                    self.fail(
                        "Assignment expression within a comprehension"
                        " cannot be used in a class body",
                        s,
                        code=codes.SYNTAX,
                        serious=True,
                        blocker=True,
                    )
                    return False
                break
        return True

    def visit_assignment_stmt(self, s: AssignmentStmt) -> None:
        self.statement = s

        # Special case assignment like X = X.
        if self.analyze_identity_global_assignment(s):
            return

        tag = self.track_incomplete_refs()

        # Here we have a chicken and egg problem: at this stage we can't call
        # can_be_type_alias(), because we have not enough information about rvalue.
        # But we can't use a full visit because it may emit extra incomplete refs (namely
        # when analysing any type applications there) thus preventing the further analysis.
        # To break the tie, we first analyse rvalue partially, if it can be a type alias.
        if self.can_possibly_be_type_form(s):
            old_basic_type_applications = self.basic_type_applications
            self.basic_type_applications = True
            with self.allow_unbound_tvars_set():
                s.rvalue.accept(self)
            self.basic_type_applications = old_basic_type_applications
        elif self.can_possibly_be_typevarlike_declaration(s):
            # Allow unbound tvars inside TypeVarLike defaults to be evaluated later
            with self.allow_unbound_tvars_set():
                s.rvalue.accept(self)
        else:
            s.rvalue.accept(self)

        if self.found_incomplete_ref(tag) or self.should_wait_rhs(s.rvalue):
            # Initializer couldn't be fully analyzed. Defer the current node and give up.
            # Make sure that if we skip the definition of some local names, they can't be
            # added later in this scope, since an earlier definition should take precedence.
            for expr in names_modified_by_assignment(s):
                self.mark_incomplete(expr.name, expr)
            return
        if self.can_possibly_be_type_form(s):
            # Now re-visit those rvalues that were we skipped type applications above.
            # This should be safe as generally semantic analyzer is idempotent.
            with self.allow_unbound_tvars_set():
                s.rvalue.accept(self)

        # The r.h.s. is now ready to be classified, first check if it is a special form:
        special_form = False
        # * type alias
        if self.check_and_set_up_type_alias(s):
            s.is_alias_def = True
            special_form = True
        elif isinstance(s.rvalue, CallExpr):
            # * type variable definition
            if self.process_typevar_declaration(s):
                special_form = True
            elif self.process_paramspec_declaration(s):
                special_form = True
            elif self.process_typevartuple_declaration(s):
                special_form = True
            # * type constructors
            elif self.analyze_namedtuple_assign(s):
                special_form = True
            elif self.analyze_typeddict_assign(s):
                special_form = True
            elif self.newtype_analyzer.process_newtype_declaration(s):
                special_form = True
            elif self.analyze_enum_assign(s):
                special_form = True

        if special_form:
            self.record_special_form_lvalue(s)
            return
        # Clear the alias flag if assignment turns out not a special form after all. It
        # may be set to True while there were still placeholders due to forward refs.
        s.is_alias_def = False

        # OK, this is a regular assignment, perform the necessary analysis steps.
        s.is_final_def = self.unwrap_final(s)
        self.analyze_lvalues(s)
        self.check_final_implicit_def(s)
        self.store_final_status(s)
        self.check_classvar(s)
        self.process_type_annotation(s)
        self.apply_dynamic_class_hook(s)
        if not s.type:
            self.process_module_assignment(s.lvalues, s.rvalue, s)
        self.process__all__(s)
        self.process__deletable__(s)
        self.process__slots__(s)

    def analyze_identity_global_assignment(self, s: AssignmentStmt) -> bool:
        """Special case 'X = X' in global scope.

        This allows supporting some important use cases.

        Return true if special casing was applied.
        """
        if not isinstance(s.rvalue, NameExpr) or len(s.lvalues) != 1:
            # Not of form 'X = X'
            return False
        lvalue = s.lvalues[0]
        if not isinstance(lvalue, NameExpr) or s.rvalue.name != lvalue.name:
            # Not of form 'X = X'
            return False
        if self.type is not None or self.is_func_scope():
            # Not in global scope
            return False
        # It's an assignment like 'X = X' in the global scope.
        name = lvalue.name
        sym = self.lookup(name, s)
        if sym is None:
            if self.final_iteration:
                # Fall back to normal assignment analysis.
                return False
            else:
                self.defer()
                return True
        else:
            if sym.node is None:
                # Something special -- fall back to normal assignment analysis.
                return False
            if name not in self.globals:
                # The name is from builtins. Add an alias to the current module.
                self.add_symbol(name, sym.node, s)
            if not isinstance(sym.node, PlaceholderNode):
                for node in s.rvalue, lvalue:
                    node.node = sym.node
                    node.kind = GDEF
                    node.fullname = sym.node.fullname
            return True

    def should_wait_rhs(self, rv: Expression) -> bool:
        """Can we already classify this r.h.s. of an assignment or should we wait?

        This returns True if we don't have enough information to decide whether
        an assignment is just a normal variable definition or a special form.
        Always return False if this is a final iteration. This will typically cause
        the lvalue to be classified as a variable plus emit an error.
        """
        if self.final_iteration:
            # No chance, nothing has changed.
            return False
        if isinstance(rv, NameExpr):
            n = self.lookup(rv.name, rv)
            if n and isinstance(n.node, PlaceholderNode) and not n.node.becomes_typeinfo:
                return True
        elif isinstance(rv, MemberExpr):
            fname = get_member_expr_fullname(rv)
            if fname:
                n = self.lookup_qualified(fname, rv, suppress_errors=True)
                if n and isinstance(n.node, PlaceholderNode) and not n.node.becomes_typeinfo:
                    return True
        elif isinstance(rv, IndexExpr) and isinstance(rv.base, RefExpr):
            return self.should_wait_rhs(rv.base)
        elif isinstance(rv, CallExpr) and isinstance(rv.callee, RefExpr):
            # This is only relevant for builtin SCC where things like 'TypeVar'
            # may be not ready.
            return self.should_wait_rhs(rv.callee)
        return False

    def can_be_type_alias(self, rv: Expression, allow_none: bool = False) -> bool:
        """Is this a valid r.h.s. for an alias definition?

        Note: this function should be only called for expressions where self.should_wait_rhs()
        returns False.
        """
        if isinstance(rv, RefExpr) and self.is_type_ref(rv, bare=True):
            return True
        if isinstance(rv, IndexExpr) and self.is_type_ref(rv.base, bare=False):
            return True
        if self.is_none_alias(rv):
            return True
        if allow_none and isinstance(rv, NameExpr) and rv.fullname == "builtins.None":
            return True
        if isinstance(rv, OpExpr) and rv.op == "|":
            if self.is_stub_file:
                return True
            if self.can_be_type_alias(rv.left, allow_none=True) and self.can_be_type_alias(
                rv.right, allow_none=True
            ):
                return True
        return False

    def can_possibly_be_type_form(self, s: AssignmentStmt) -> bool:
        """Like can_be_type_alias(), but simpler and doesn't require fully analyzed rvalue.

        Instead, use lvalues/annotations structure to figure out whether this can potentially be
        a type alias definition, NamedTuple, or TypedDict. Another difference from above function
        is that we are only interested IndexExpr, CallExpr and OpExpr rvalues, since only those
        can be potentially recursive (things like `A = A` are never valid).
        """
        if len(s.lvalues) > 1:
            return False
        if isinstance(s.rvalue, CallExpr) and isinstance(s.rvalue.callee, RefExpr):
            ref = s.rvalue.callee.fullname
            return ref in TPDICT_NAMES or ref in TYPED_NAMEDTUPLE_NAMES
        if not isinstance(s.lvalues[0], NameExpr):
            return False
        if s.unanalyzed_type is not None and not self.is_pep_613(s):
            return False
        if not isinstance(s.rvalue, (IndexExpr, OpExpr)):
            return False
        # Something that looks like Foo = Bar[Baz, ...]
        return True

    def can_possibly_be_typevarlike_declaration(self, s: AssignmentStmt) -> bool:
        """Check if r.h.s. can be a TypeVarLike declaration."""
        if len(s.lvalues) != 1 or not isinstance(s.lvalues[0], NameExpr):
            return False
        if not isinstance(s.rvalue, CallExpr) or not isinstance(s.rvalue.callee, NameExpr):
            return False
        ref = s.rvalue.callee
        ref.accept(self)
        return ref.fullname in TYPE_VAR_LIKE_NAMES

    def is_type_ref(self, rv: Expression, bare: bool = False) -> bool:
        """Does this expression refer to a type?

        This includes:
          * Special forms, like Any or Union
          * Classes (except subscripted enums)
          * Other type aliases
          * PlaceholderNodes with becomes_typeinfo=True (these can be not ready class
            definitions, and not ready aliases).

        If bare is True, this is not a base of an index expression, so some special
        forms are not valid (like a bare Union).

        Note: This method should be only used in context of a type alias definition.
        This method can only return True for RefExprs, to check if C[int] is a valid
        target for type alias call this method on expr.base (i.e. on C in C[int]).
        See also can_be_type_alias().
        """
        if not isinstance(rv, RefExpr):
            return False
        if isinstance(rv.node, TypeVarLikeExpr):
            self.fail(f'Type variable "{rv.fullname}" is invalid as target for type alias', rv)
            return False

        if bare:
            # These three are valid even if bare, for example
            # A = Tuple is just equivalent to A = Tuple[Any, ...].
            valid_refs = {"typing.Any", "typing.Tuple", "typing.Callable"}
        else:
            valid_refs = type_constructors

        if isinstance(rv.node, TypeAlias) or rv.fullname in valid_refs:
            return True
        if isinstance(rv.node, TypeInfo):
            if bare:
                return True
            # Assignment color = Color['RED'] defines a variable, not an alias.
            return not rv.node.is_enum
        if isinstance(rv.node, Var):
            return rv.node.fullname in NEVER_NAMES

        if isinstance(rv, NameExpr):
            n = self.lookup(rv.name, rv)
            if n and isinstance(n.node, PlaceholderNode) and n.node.becomes_typeinfo:
                return True
        elif isinstance(rv, MemberExpr):
            fname = get_member_expr_fullname(rv)
            if fname:
                # The r.h.s. for variable definitions may not be a type reference but just
                # an instance attribute, so suppress the errors.
                n = self.lookup_qualified(fname, rv, suppress_errors=True)
                if n and isinstance(n.node, PlaceholderNode) and n.node.becomes_typeinfo:
                    return True
        return False

    def is_none_alias(self, node: Expression) -> bool:
        """Is this a r.h.s. for a None alias?

        We special case the assignments like Void = type(None), to allow using
        Void in type annotations.
        """
        if isinstance(node, CallExpr):
            if (
                isinstance(node.callee, NameExpr)
                and len(node.args) == 1
                and isinstance(node.args[0], NameExpr)
            ):
                call = self.lookup_qualified(node.callee.name, node.callee)
                arg = self.lookup_qualified(node.args[0].name, node.args[0])
                if (
                    call is not None
                    and call.node
                    and call.node.fullname == "builtins.type"
                    and arg is not None
                    and arg.node
                    and arg.node.fullname == "builtins.None"
                ):
                    return True
        return False

    def record_special_form_lvalue(self, s: AssignmentStmt) -> None:
        """Record minimal necessary information about l.h.s. of a special form.

        This exists mostly for compatibility with the old semantic analyzer.
        """
        lvalue = s.lvalues[0]
        assert isinstance(lvalue, NameExpr)
        lvalue.is_special_form = True
        if self.current_symbol_kind() == GDEF:
            lvalue.fullname = self.qualified_name(lvalue.name)
        lvalue.kind = self.current_symbol_kind()

    def analyze_enum_assign(self, s: AssignmentStmt) -> bool:
        """Check if s defines an Enum."""
        if isinstance(s.rvalue, CallExpr) and isinstance(s.rvalue.analyzed, EnumCallExpr):
            # Already analyzed enum -- nothing to do here.
            return True
        return self.enum_call_analyzer.process_enum_call(s, self.is_func_scope())

    def analyze_namedtuple_assign(self, s: AssignmentStmt) -> bool:
        """Check if s defines a namedtuple."""
        if isinstance(s.rvalue, CallExpr) and isinstance(s.rvalue.analyzed, NamedTupleExpr):
            if s.rvalue.analyzed.info.tuple_type and not has_placeholder(
                s.rvalue.analyzed.info.tuple_type
            ):
                return True  # This is a valid and analyzed named tuple definition, nothing to do here.
        if len(s.lvalues) != 1 or not isinstance(s.lvalues[0], (NameExpr, MemberExpr)):
            return False
        lvalue = s.lvalues[0]
        if isinstance(lvalue, MemberExpr):
            if isinstance(s.rvalue, CallExpr) and isinstance(s.rvalue.callee, RefExpr):
                fullname = s.rvalue.callee.fullname
                if fullname == "collections.namedtuple" or fullname in TYPED_NAMEDTUPLE_NAMES:
                    self.fail("NamedTuple type as an attribute is not supported", lvalue)
            return False
        name = lvalue.name
        namespace = self.qualified_name(name)
        with self.tvar_scope_frame(self.tvar_scope.class_frame(namespace)):
            internal_name, info, tvar_defs = self.named_tuple_analyzer.check_namedtuple(
                s.rvalue, name, self.is_func_scope()
            )
            if internal_name is None:
                return False
            if internal_name != name:
                self.fail(
                    'First argument to namedtuple() should be "{}", not "{}"'.format(
                        name, internal_name
                    ),
                    s.rvalue,
                    code=codes.NAME_MATCH,
                )
                return True
            # Yes, it's a valid namedtuple, but defer if it is not ready.
            if not info:
                self.mark_incomplete(name, lvalue, becomes_typeinfo=True)
            else:
                self.setup_type_vars(info.defn, tvar_defs)
                self.setup_alias_type_vars(info.defn)
            return True

    def analyze_typeddict_assign(self, s: AssignmentStmt) -> bool:
        """Check if s defines a typed dict."""
        if isinstance(s.rvalue, CallExpr) and isinstance(s.rvalue.analyzed, TypedDictExpr):
            if s.rvalue.analyzed.info.typeddict_type and not has_placeholder(
                s.rvalue.analyzed.info.typeddict_type
            ):
                # This is a valid and analyzed typed dict definition, nothing to do here.
                return True
        if len(s.lvalues) != 1 or not isinstance(s.lvalues[0], (NameExpr, MemberExpr)):
            return False
        lvalue = s.lvalues[0]
        name = lvalue.name
        namespace = self.qualified_name(name)
        with self.tvar_scope_frame(self.tvar_scope.class_frame(namespace)):
            is_typed_dict, info, tvar_defs = self.typed_dict_analyzer.check_typeddict(
                s.rvalue, name, self.is_func_scope()
            )
            if not is_typed_dict:
                return False
            if isinstance(lvalue, MemberExpr):
                self.fail("TypedDict type as attribute is not supported", lvalue)
                return False
            # Yes, it's a valid typed dict, but defer if it is not ready.
            if not info:
                self.mark_incomplete(name, lvalue, becomes_typeinfo=True)
            else:
                defn = info.defn
                self.setup_type_vars(defn, tvar_defs)
                self.setup_alias_type_vars(defn)
            return True

    def analyze_lvalues(self, s: AssignmentStmt) -> None:
        # We cannot use s.type, because analyze_simple_literal_type() will set it.
        explicit = s.unanalyzed_type is not None
        if self.is_final_type(s.unanalyzed_type):
            # We need to exclude bare Final.
            assert isinstance(s.unanalyzed_type, UnboundType)
            if not s.unanalyzed_type.args:
                explicit = False

        if s.rvalue:
            if isinstance(s.rvalue, TempNode):
                has_explicit_value = not s.rvalue.no_rhs
            else:
                has_explicit_value = True
        else:
            has_explicit_value = False

        for lval in s.lvalues:
            self.analyze_lvalue(
                lval,
                explicit_type=explicit,
                is_final=s.is_final_def,
                has_explicit_value=has_explicit_value,
            )

    def apply_dynamic_class_hook(self, s: AssignmentStmt) -> None:
        if not isinstance(s.rvalue, CallExpr):
            return
        fname = ""
        call = s.rvalue
        while True:
            if isinstance(call.callee, RefExpr):
                fname = call.callee.fullname
            # check if method call
            if not fname and isinstance(call.callee, MemberExpr):
                callee_expr = call.callee.expr
                if isinstance(callee_expr, RefExpr) and callee_expr.fullname:
                    method_name = call.callee.name
                    fname = callee_expr.fullname + "." + method_name
                elif (
                    isinstance(callee_expr, IndexExpr)
                    and isinstance(callee_expr.base, RefExpr)
                    and isinstance(callee_expr.analyzed, TypeApplication)
                ):
                    method_name = call.callee.name
                    fname = callee_expr.base.fullname + "." + method_name
                elif isinstance(callee_expr, CallExpr):
                    # check if chain call
                    call = callee_expr
                    continue
            break
        if not fname:
            return
        hook = self.plugin.get_dynamic_class_hook(fname)
        if not hook:
            return
        for lval in s.lvalues:
            if not isinstance(lval, NameExpr):
                continue
            hook(DynamicClassDefContext(call, lval.name, self))

    def unwrap_final(self, s: AssignmentStmt) -> bool:
        """Strip Final[...] if present in an assignment.

        This is done to invoke type inference during type checking phase for this
        assignment. Also, Final[...] doesn't affect type in any way -- it is rather an
        access qualifier for given `Var`.

        Also perform various consistency checks.

        Returns True if Final[...] was present.
        """
        if not s.unanalyzed_type or not self.is_final_type(s.unanalyzed_type):
            return False
        assert isinstance(s.unanalyzed_type, UnboundType)
        if len(s.unanalyzed_type.args) > 1:
            self.fail("Final[...] takes at most one type argument", s.unanalyzed_type)
        invalid_bare_final = False
        if not s.unanalyzed_type.args:
            s.type = None
            if (
                isinstance(s.rvalue, TempNode)
                and s.rvalue.no_rhs
                # Filter duplicate errors, we already reported this:
                and not (self.type and self.type.is_named_tuple)
            ):
                invalid_bare_final = True
                self.fail("Type in Final[...] can only be omitted if there is an initializer", s)
        else:
            s.type = s.unanalyzed_type.args[0]

        if (
            s.type is not None
            and self.options.python_version < (3, 13)
            and self.is_classvar(s.type)
        ):
            self.fail("Variable should not be annotated with both ClassVar and Final", s)
            return False

        if len(s.lvalues) != 1 or not isinstance(s.lvalues[0], RefExpr):
            self.fail("Invalid final declaration", s)
            return False
        lval = s.lvalues[0]
        assert isinstance(lval, RefExpr)

        # Reset inferred status if it was set due to simple literal rvalue on previous iteration.
        # TODO: this is a best-effort quick fix, we should avoid the need to manually sync this,
        # see https://github.com/python/mypy/issues/6458.
        if lval.is_new_def:
            lval.is_inferred_def = s.type is None

        if self.loop_depth[-1] > 0:
            self.fail("Cannot use Final inside a loop", s)
        if self.type and self.type.is_protocol:
            if self.is_class_scope():
                self.msg.protocol_members_cant_be_final(s)
        if (
            isinstance(s.rvalue, TempNode)
            and s.rvalue.no_rhs
            and not self.is_stub_file
            and not self.is_class_scope()
        ):
            if not invalid_bare_final:  # Skip extra error messages.
                self.msg.final_without_value(s)
        return True

    def check_final_implicit_def(self, s: AssignmentStmt) -> None:
        """Do basic checks for final declaration on self in __init__.

        Additional re-definition checks are performed by `analyze_lvalue`.
        """
        if not s.is_final_def:
            return
        lval = s.lvalues[0]
        assert isinstance(lval, RefExpr)
        if isinstance(lval, MemberExpr):
            if not self.is_self_member_ref(lval):
                self.fail("Final can be only applied to a name or an attribute on self", s)
                s.is_final_def = False
                return
            else:
                assert self.function_stack
                if self.function_stack[-1].name != "__init__":
                    self.fail("Can only declare a final attribute in class body or __init__", s)
                    s.is_final_def = False
                    return

    def store_final_status(self, s: AssignmentStmt) -> None:
        """If this is a locally valid final declaration, set the corresponding flag on `Var`."""
        if s.is_final_def:
            if len(s.lvalues) == 1 and isinstance(s.lvalues[0], RefExpr):
                node = s.lvalues[0].node
                if isinstance(node, Var):
                    node.is_final = True
                    if s.type:
                        node.final_value = constant_fold_expr(s.rvalue, self.cur_mod_id)
                    if self.is_class_scope() and (
                        isinstance(s.rvalue, TempNode) and s.rvalue.no_rhs
                    ):
                        node.final_unset_in_class = True
        else:
            for lval in self.flatten_lvalues(s.lvalues):
                # Special case: we are working with an `Enum`:
                #
                #   class MyEnum(Enum):
                #       key = 'some value'
                #
                # Here `key` is implicitly final. In runtime, code like
                #
                #     MyEnum.key = 'modified'
                #
                # will fail with `AttributeError: Cannot reassign members.`
                # That's why we need to replicate this.
                if (
                    isinstance(lval, NameExpr)
                    and isinstance(self.type, TypeInfo)
                    and self.type.is_enum
                ):
                    cur_node = self.type.names.get(lval.name, None)
                    if (
                        cur_node
                        and isinstance(cur_node.node, Var)
                        and not (isinstance(s.rvalue, TempNode) and s.rvalue.no_rhs)
                    ):
                        # Double underscored members are writable on an `Enum`.
                        # (Except read-only `__mem