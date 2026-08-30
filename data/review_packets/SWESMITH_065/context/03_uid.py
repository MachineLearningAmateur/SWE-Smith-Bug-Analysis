# Copyright 2008-2022 pydicom authors. See LICENSE file for details.
"""Functions for handling DICOM unique identifiers (UIDs)"""

import hashlib
import re
import secrets
import uuid
import warnings

from pydicom import config
from pydicom._uid_dict import UID_dictionary
from pydicom.config import disable_value_validation
from pydicom.valuerep import STR_VR_REGEXES, validate_value
from typing import Any

_deprecations = {
    "JPEGBaseline": "JPEGBaseline8Bit",
    "JPEGExtended": "JPEGExtended12Bit",
    "JPEGLossless": "JPEGLosslessSV1",
    "JPEGLSLossy": "JPEGLSNearLossless",
    "JPEG2000MultiComponentLossless": "JPEG2000MCLossless",
    "JPEG2000MultiComponent": "JPEG2000MC",
}

def __getattr__(name: str) -> Any:
    if name in _deprecations:
        replacement = _deprecations[name]
        if name == "JPEGLossless":
            warnings.warn(
                "In pydicom v3.0 the UID for 'JPEGLossless' will change "
                "from '1.2.840.10008.1.2.4.70' to '1.2.840.10008.1.2.4.57' to "
                f"match its UID keyword. Use '{replacement}' instead"
            )
        else:
            warnings.warn(
                f"The UID constant '{name}' is deprecated and will be removed "
                f"in pydicom v3.0, use '{replacement}' instead",
                DeprecationWarning,
            )

        return globals()[replacement]

    raise AttributeError(f"module {__name__} has no attribute {name}")

class UID(str):
    """Human friendly UIDs as a Python :class:`str` subclass.

    **Private Transfer Syntaxes**

    If creating a private transfer syntax UID, then you must also use
    :meth:`~pydicom.UID.set_private_encoding` to set the corresponding
    dataset encoding.

    Examples
    --------

    General usage::

      >>> from pydicom.uid import UID
      >>> uid = UID('1.2.840.10008.1.2.4.50')
      >>> uid
      '1.2.840.10008.1.2.4.50'
      >>> uid.is_implicit_VR
      False
      >>> uid.is_little_endian
      True
      >>> uid.is_transfer_syntax
      True
      >>> uid.name
      'JPEG Baseline (Process 1)'
      >>> uid.keyword
      JPEGBaseline8Bit

    Setting the encoding to explicit VR little endian for a private transfer
    syntax::

      >>> uid = UID("1.2.3.4")
      >>> uid.set_private_encoding(False, True)

    """

    _PRIVATE_TS_ENCODING: tuple[bool, bool]

    def __new__(
        cls: type["UID"], val: str, validation_mode: int | None = None
    ) -> "UID":
        """Setup new instance of the class.

        Parameters
        ----------
        val : str or pydicom.uid.UID
            The UID string to use to create the UID object.
        validation_mode : int
            Defines if values are validated and how validation errors are
            handled.

        Returns
        -------
        pydicom.uid.UID
            The UID object.
        """
        if isinstance(val, str):
            if validation_mode is None:
                validation_mode = config.settings.reading_validation_mode
            validate_value("UI", val, validation_mode)

            uid = super().__new__(cls, val.strip())
            if hasattr(val, "_PRIVATE_TS_ENCODING"):
                uid._PRIVATE_TS_ENCODING = val._PRIVATE_TS_ENCODING

            return uid

        raise TypeError("A UID must be created from a string")

    @property
    def is_implicit_VR(self) -> bool:
        """Return ``True`` if an implicit VR transfer syntax UID."""
        if self.is_transfer_syntax:
            if not self.is_private:
                # Implicit VR Little Endian
                if self == "1.2.840.10008.1.2":
                    return True

                # Explicit VR Little Endian
                # Explicit VR Big Endian
                # Deflated Explicit VR Little Endian
                # All encapsulated transfer syntaxes
                return False

            return self._PRIVATE_TS_ENCODING[0]

        raise ValueError("UID is not a transfer syntax.")

    @property
    def is_little_endian(self) -> bool:
        """Return ``True`` if a little endian transfer syntax UID."""
        if self.is_transfer_syntax:
            if not self.is_private:
                # Explicit VR Big Endian
                if self == "1.2.840.10008.1.2.2":
                    return False

                # Explicit VR Little Endian
                # Implicit VR Little Endian
                # Deflated Explicit VR Little Endian
                # All encapsulated transfer syntaxes
                return True

            return self._PRIVATE_TS_ENCODING[1]

        raise ValueError("UID is not a transfer syntax.")

    @property
    def is_transfer_syntax(self) -> bool:
        """Return ``True`` if a transfer syntax UID."""
        if not self.is_private:
            return self.type == "Transfer Syntax"

        return hasattr(self, "_PRIVATE_TS_ENCODING")

    @property
    def is_deflated(self) -> bool:
        """Return ``True`` if a deflated transfer syntax UID."""
        if self.is_transfer_syntax:
            # Deflated Explicit VR Little Endian
            if self == "1.2.840.10008.1.2.1.99":
                return True

            # Explicit VR Little Endian
            # Implicit VR Little Endian
            # Explicit VR Big Endian
            # All encapsulated transfer syntaxes
            return False

        raise ValueError("UID is not a transfer syntax.")

    @property
    def is_encapsulated(self) -> bool:
        """Return ``True`` if an encasulated transfer syntax UID."""
        return self.is_compressed

    @property
    def is_compressed(self) -> bool:
        """Return ``True`` if a compressed transfer syntax UID."""
        if self.is_transfer_syntax:
            # Explicit VR Little Endian
            # Implicit VR Little Endian
            # Explicit VR Big Endian
            # Deflated Explicit VR Little Endian
            if self in [
                "1.2.840.10008.1.2",
                "1.2.840.10008.1.2.1",
                "1.2.840.10008.1.2.2",
                "1.2.840.10008.1.2.1.99",
            ]:
                return False

            # All encapsulated transfer syntaxes
            return True

        raise ValueError("UID is not a transfer syntax.")

    @property
    def keyword(self) -> str:
        """Return the UID keyword from the UID dictionary."""
        if str(self) in UID_dictionary:
            return UID_dictionary[self][4]

        return ""

    @property
    def name(self) -> str:
        """Return the UID name from the UID dictionary."""
        uid_string = str(self)
        if uid_string in UID_dictionary:
            return UID_dictionary[self][0]

        return uid_string

    @property
    def type(self) -> str:
        """Return the UID type from the UID dictionary."""
        if str(self) in UID_dictionary:
            return UID_dictionary[self][1]

        return ""

    @property
    def info(self) -> str:
        """Return the UID info from the UID dictionary."""
        if str(self) in UID_dictionary:
            return UID_dictionary[self][2]

        return ""

    @property
    def is_retired(self) -> bool:
        """Return ``True`` if the UID is retired, ``False`` otherwise or if
        private.
        """
        if str(self) in UID_dictionary:
            return bool(UID_dictionary[self][3])

        return False

    @property
    def is_private(self) -> bool:
        """Return ``True`` if the UID isn't an officially registered DICOM
        UID.
        """
        return self[:14] != "1.2.840.10008."

    @property
    def is_valid(self) -> bool:
        """Return ``True`` if `self` is a valid UID, ``False`` otherwise."""
        if len(self) <= 64 and re.match(RE_VALID_UID, self):
            return True

        return False

    def set_private_encoding(self, implicit_vr: bool, little_endian: bool) -> None:
        """Set the corresponding dataset encoding for a privately defined transfer
        syntax.

        .. versionadded:: 3.0

        Parameters
        ----------
        implicit_vr : bool
            ``True`` if the corresponding dataset encoding uses implicit VR,
            ``False`` for explicit VR.
        little_endian : bool
            ``True`` if the corresponding dataset encoding uses little endian
            byte order, ``False`` for big endian byte order.
        """
        self._PRIVATE_TS_ENCODING = (implicit_vr, little_endian)


# Many thanks to the Medical Connections for offering free
# valid UIDs (https://www.medicalconnections.co.uk/FreeUID.html)
# Their service was used to obtain the following root UID for pydicom:
PYDICOM_ROOT_UID = "1.2.826.0.1.3680043.8.498."
"""pydicom's root UID ``'1.2.826.0.1.3680043.8.498.'``"""
PYDICOM_IMPLEMENTATION_UID = UID(f"{PYDICOM_ROOT_UID}1")
"""
pydicom's (0002,0012) *Implementation Class UID*
``'1.2.826.0.1.3680043.8.498.1'``
"""

# Regexes for valid UIDs and valid UID prefixes
RE_VALID_UID = STR_VR_REGEXES["UI"]
"""Regex for a valid UID"""
RE_VALID_UID_PREFIX = re.compile(r"^(0|[1-9][0-9]*)(\.(0|[1-9][0-9]*))*\.$")
"""Regex for a valid UID prefix"""

with disable_value_validation():
    # Pre-defined Transfer Syntax UIDs (for convenience)
    ImplicitVRLittleEndian = UID("1.2.840.10008.1.2")
    """1.2.840.10008.1.2"""
    ExplicitVRLittleEndian = UID("1.2.840.10008.1.2.1")
    """1.2.840.10008.1.2.1"""
    DeflatedExplicitVRLittleEndian = UID("1.2.840.10008.1.2.1.99")
    """1.2.840.10008.1.2.1.99"""
    ExplicitVRBigEndian = UID("1.2.840.10008.1.2.2")
    """1.2.840.10008.1.2.2"""
    JPEGBaseline8Bit = UID("1.2.840.10008.1.2.4.50")
    """1.2.840.10008.1.2.4.50"""
    JPEGExtended12Bit = UID("1.2.840.10008.1.2.4.51")
    """1.2.840.10008.1.2.4.51"""
    JPEGLosslessP14 = UID("1.2.840.10008.1.2.4.57")  # needs to be updated
    """1.2.840.10008.1.2.4.57"""
    JPEGLosslessSV1 = UID("1.2.840.10008.1.2.4.70")  # Old JPEGLossless
    """1.2.840.10008.1.2.4.70"""
    JPEGLSLossless = UID("1.2.840.10008.1.2.4.80")
    """1.2.840.10008.1.2.4.80"""
    JPEGLSNearLossless = UID("1.2.840.10008.1.2.4.81")
    """1.2.840.10008.1.2.4.81"""
    JPEG2000Lossless = UID("1.2.840.10008.1.2.4.90")
    """1.2.840.10008.1.2.4.90"""
    JPEG2000 = UID("1.2.840.10008.1.2.4.91")
    """1.2.840.10008.1.2.4.91"""
    JPEG2000MCLossless = UID("1.2.840.10008.1.2.4.92")
    """1.2.840.10008.1.2.4.92"""
    JPEG2000MC = UID("1.2.840.10008.1.2.4.93")
    """1.2.840.10008.1.2.4.93"""
    MPEG2MPML = UID("1.2.840.10008.1.2.4.100")
    """1.2.840.10008.1.2.4.100"""
    MPEG2MPHL = UID("1.2.840.10008.1.2.4.101")
    """1.2.840.10008.1.2.4.101"""
    MPEG4HP41 = UID("1.2.840.10008.1.2.4.102")
    """1.2.840.10008.1.2.4.102"""
    MPEG4HP41BD = UID("1.2.840.10008.1.2.4.103")
    """1.2.840.10008.1.2.4.103"""
    MPEG4HP422D = UID("1.2.840.10008.1.2.4.104")
    """1.2.840.10008.1.2.4.104"""
    MPEG4HP423D = UID("1.2.840.10008.1.2.4.105")
    """1.2.840.10008.1.2.4.105"""
    MPEG4HP42STEREO = UID("1.2.840.10008.1.2.4.106")
    """1.2.840.10008.1.2.4.106"""
    HEVCMP51 = UID("1.2.840.10008.1.2.4.107")
    """1.2.840.10008.1.2.4.107"""
    HEVCM10P51 = UID("1.2.840.10008.1.2.4.108")
    """1.2.840.10008.1.2.4.108"""
    RLELossless = UID("1.2.840.10008.1.2.5")
    """1.2.840.10008.1.2.5"""

    AllTransferSyntaxes = [
        ImplicitVRLittleEndian,
        ExplicitVRLittleEndian,
        DeflatedExplicitVRLittleEndian,
        ExplicitVRBigEndian,
        JPEGBaseline8Bit,
        JPEGExtended12Bit,
        JPEGLosslessP14,
        JPEGLosslessSV1,
        JPEGLSLossless,
        JPEGLSNearLossless,
        JPEG2000Lossless,
        JPEG2000,
        JPEG2000MCLossless,
        JPEG2000MC,
        MPEG2MPML,
        MPEG2MPHL,
        MPEG4HP41,
        MPEG4HP41BD,
        MPEG4HP422D,
        MPEG4HP423D,
        MPEG4HP42STEREO,
        HEVCMP51,
        HEVCM10P51,
        RLELossless,
    ]
    """All non-retired transfer syntaxes and *Explicit VR Big Endian*."""

    JPEGTransferSyntaxes = [
        JPEGBaseline8Bit,
        JPEGExtended12Bit,
        JPEGLosslessP14,
        JPEGLosslessSV1,
    ]
    """JPEG (ISO/IEC 10918-1) transfer syntaxes"""

    JPEGLSTransferSyntaxes = [JPEGLSLossless, JPEGLSNearLossless]
    """JPEG-LS (ISO/IEC 14495-1) transfer syntaxes."""

    JPEG2000TransferSyntaxes = [
        JPEG2000Lossless,
        JPEG2000,
        JPEG2000MCLossless,
        JPEG2000MC,
        HTJ2KLossless,
        HTJ2KLosslessRPCL,
        HTJ2K,
    ]
    """JPEG 2000 (ISO/IEC 15444-1) transfer syntaxes."""

    JPEGXLTransferSyntaxes = [JPEGXLLossless, JPEGXLJPEGRecompression, JPEGXL]
    """JPEG XL (ISO/IEC 18181-1) transfer syntaxes."""

    MPEGTransferSyntaxes = [
        MPEG2MPML,
        MPEG2MPHL,
        MPEG4HP41,
        MPEG4HP41BD,
        MPEG4HP422D,
        MPEG4HP423D,
        MPEG4HP42STEREO,
        HEVCMP51,
        HEVCM10P51,
    ]
    """MPEG transfer syntaxes."""

    RLETransferSyntaxes = [RLELossless]
    """RLE transfer syntaxes."""

    UncompressedTransferSyntaxes = [
        ExplicitVRLittleEndian,
        ImplicitVRLittleEndian,
        DeflatedExplicitVRLittleEndian,
        ExplicitVRBigEndian,
    ]
    """Uncompressed (native) transfer syntaxes."""

    PrivateTransferSyntaxes = []
    """Private transfer syntaxes added using the
    :func:`~pydicom.uid.register_transfer_syntax` function.
    """

def register_transfer_syntax(
    uid: str | UID,
    implicit_vr: bool | None = None,
    little_endian: bool | None = None,
) -> UID:
    """Register a private transfer syntax with the :mod:`~pydicom.uid` module
    so it can be used when reading datasets with :func:`~pydicom.filereader.dcmread`.

    .. versionadded: 3.0

    Parameters
    ----------
    uid : str | pydicom.uid.UID
        A UID which may or may not have had the corresponding dataset encoding
        set using :meth:`~pydicom.uid.UID.set_private_encoding`.
    implicit_vr : bool, optional
        If ``True`` then the transfer syntax uses implicit VR encoding, otherwise
        if ``False`` then it uses explicit VR encoding. Required when `uid` has
        not had the encoding set using :meth:`~pydicom.uid.UID.set_private_encoding`.
    little_endian : bool, optional
        If ``True`` then the transfer syntax uses little endian encoding, otherwise
        if ``False`` then it uses big endian encoding. Required when `uid` has
        not had the encoding set using :meth:`~pydicom.uid.UID.set_private_encoding`.

    Returns
    -------
    pydicom.uid.UID
        The registered UID.
    """
    uid = UID(uid)

    if None in (implicit_vr, little_endian) and not uid.is_transfer_syntax:
        raise ValueError(
            "The corresponding dataset encoding for 'uid' must be set using "
            "the 'implicit_vr' and 'little_endian' arguments"
        )

    if implicit_vr is not None and little_endian is not None:
        uid.set_private_encoding(implicit_vr, little_endian)

    if uid not in PrivateTransferSyntaxes:
        PrivateTransferSyntaxes.append(uid)

    return uid


_MAX_PREFIX_LENGTH = 54


def generate_uid(
    prefix: str | None = PYDICOM_ROOT_UID,
    entropy_srcs: list[str] | None = None,
) -> UID:
    """Return a 64 character UID which starts with `prefix`.

    .. versionchanged:: 3.0

       * When `entropy_srcs` is ``None`` the suffix is now generated using
         :func:`~secrets.randbelow`
       * The maximum length of `prefix` is now 54 characters

    Parameters
    ----------
    prefix : str or None, optional
        The UID prefix to use when creating the UID. Default is the *pydicom*
        root UID ``'1.2.826.0.1.3680043.8.498.'``. If `prefix` is ``None`` then
        a prefix of ``'2.25.'`` will be used with the integer form of a UUID
        generated using the :func:`uuid.uuid4` algorithm.
    entropy_srcs : list of str, optional
        If `prefix` is used then the `prefix` will be appended with a
        SHA512 hash of the supplied :class:`list` which means the result is
        deterministic and should make the original data unrecoverable. If
        `entropy_srcs` isn't used then a random number from
        :func:`secrets.randbelow` will be appended to the `prefix`. If `prefix`
        is ``None`` then `entropy_srcs` has no effect.

    Returns
    -------
    pydicom.uid.UID
        A DICOM UID of up to 64 characters.

    Raises
    ------
    ValueError
        If `prefix` is invalid or greater than 54 characters.

    Examples
    --------

    >>> from pydicom.uid import generate_uid
    >>> generate_uid()
    1.2.826.0.1.3680043.8.498.22463838056059845879389038257786771680
    >>> generate_uid(prefix=None)
    2.25.167161297070865690102504091919570542144
    >>> generate_uid(entropy_srcs=['lorem', 'ipsum'])
    1.2.826.0.1.3680043.8.498.87507166259346337659265156363895084463
    >>> generate_uid(entropy_srcs=['lorem', 'ipsum'])
    1.2.826.0.1.3680043.8.498.87507166259346337659265156363895084463

    References
    ----------

    * DICOM Standard, Part 5, :dcm:`Chapters 9<part05/chapter_9.html>` and
      :dcm:`Annex B<part05/chapter_B.html>`
    * ISO/IEC 9834-8/`ITU-T X.667 <https://www.itu.int/rec/T-REC-X.667-201210-I/en>`_
    """
    if prefix is None:
        # UUID -> as 128-bit int -> max 39 characters long
        return UID(f"2.25.{uuid.uuid4().int}")

    if len(prefix) > _MAX_PREFIX_LENGTH:
        raise ValueError(
            f"The 'prefix' should be no more than {_MAX_PREFIX_LENGTH} characters long"
        )

    if not re.match(RE_VALID_UID_PREFIX, prefix):
        raise ValueError(
            "The 'prefix' is not valid for use with a UID, see Part 5, Section "
            "9.1 of the DICOM Standard"
        )

    if entropy_srcs is None:
        maximum = 10 ** (64 - len(prefix))
        # randbelow is in [0, maximum)
        # {prefix}.0, and {prefix}0 are both valid
        return UID(f"{prefix}{secrets.randbelow(maximum)}"[:64])

    hash_val = hashlib.sha512("".join(entropy_srcs).encode("utf-8"))

    # Convert this to an int with the maximum available digits
    return UID(f"{prefix}{int(hash_val.hexdigest(), 16)}"[:64])


# Deprecated
if sys.version_info[:2] < (3, 7):
    JPEGBaseline = JPEGBaseline8Bit
    JPEGExtended = JPEGExtended12Bit
    JPEGLossless = JPEGLosslessSV1
    JPEGLSLossy = JPEGLSNearLossless
    JPEG2000MultiComponentLossless = JPEG2000MCLossless
    JPEG2000MultiComponent = JPEG2000MC

JPEGLossyCompressedPixelTransferSyntaxes = [
    JPEGBaseline8Bit,
    JPEGExtended12Bit,
]
JPEGLSSupportedCompressedPixelTransferSyntaxes = JPEGLSTransferSyntaxes
JPEG2000CompressedPixelTransferSyntaxes = JPEG2000TransferSyntaxes
PILSupportedCompressedPixelTransferSyntaxes = [
    JPEGBaseline8Bit,
    JPEGLosslessP14,
    JPEGExtended12Bit,
    JPEG2000Lossless,
    JPEG2000,
]
RLECompressedLosslessSyntaxes = RLETransferSyntaxes
UncompressedPixelTransferSyntaxes = UncompressedTransferSyntaxes