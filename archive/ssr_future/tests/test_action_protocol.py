"""The textual action protocol must be forgiving outside the block and
strict inside it. A model that gets the format slightly wrong should get a
usable error, not a silently dropped action."""

import pytest

from ssr.action_protocol import ProtocolError, parse_action


def test_simple_shell():
    action = parse_action("ACTION: SHELL\nCOMMAND: git log --oneline -20")
    assert action.name == "SHELL"
    assert action.get("COMMAND") == "git log --oneline -20"


def test_read():
    action = parse_action("ACTION: READ\nPATH: src/foo.py")
    assert action.name == "READ"
    assert action.get("PATH") == "src/foo.py"


def test_block_value():
    reply = "ACTION: WRITE\nPATH: a.py\nCONTENT:\n<<<END\nline one\nline two\nEND"
    action = parse_action(reply)
    assert action.get("CONTENT") == "line one\nline two"


def test_block_body_may_contain_a_colon_line():
    reply = "ACTION: WRITE\nPATH: a.py\nCONTENT:\n<<<END\nKEY: not a header\nEND"
    assert parse_action(reply).get("CONTENT") == "KEY: not a header"


def test_two_blocks():
    reply = "ACTION: EDIT\nPATH: a.py\nOLD:\n<<<END\nold\nEND\nNEW:\n<<<END\nnew\nEND"
    action = parse_action(reply)
    assert action.get("OLD") == "old"
    assert action.get("NEW") == "new"


def test_empty_new_block_is_a_deletion():
    reply = "ACTION: EDIT\nPATH: a.py\nOLD:\n<<<END\nold\nEND\nNEW:\n<<<END\nEND"
    assert parse_action(reply).get("NEW") == ""


def test_prose_around_the_block_is_tolerated():
    reply = "I will look at the log now.\n\nACTION: SHELL\nCOMMAND: ls\n\nThat should show it."
    assert parse_action(reply).name == "SHELL"


def test_markdown_fence_around_the_whole_reply():
    reply = "```\nACTION: GIT_STATUS\n```"
    assert parse_action(reply).name == "GIT_STATUS"


def test_second_action_is_ignored_but_counted():
    reply = "ACTION: SHELL\nCOMMAND: ls\nACTION: SHELL\nCOMMAND: pwd"
    action = parse_action(reply)
    assert action.get("COMMAND") == "ls"
    assert action.trailing_actions == 1


def test_no_action_line():
    with pytest.raises(ProtocolError, match="No 'ACTION"):
        parse_action("I think we should look at the parser.")


def test_unknown_action():
    with pytest.raises(ProtocolError, match="Unknown action"):
        parse_action("ACTION: TELEPORT\nPATH: x")


def test_missing_required_field():
    with pytest.raises(ProtocolError, match="missing required field"):
        parse_action("ACTION: READ")


def test_unclosed_block_names_the_marker():
    reply = "ACTION: WRITE\nPATH: a.py\nCONTENT:\n<<<END\nbody without a close"
    with pytest.raises(ProtocolError, match="never closed"):
        parse_action(reply)


def test_empty_reply():
    with pytest.raises(ProtocolError, match="Empty reply"):
        parse_action("   ")


def test_finish_carries_extra_fields():
    reply = "ACTION: FINISH\nSUMMARY: done\nREVERTED_COMMITS:\n<<<END\nabc1234\nEND"
    action = parse_action(reply)
    assert action.get("SUMMARY") == "done"
    assert action.get("REVERTED_COMMITS") == "abc1234"
