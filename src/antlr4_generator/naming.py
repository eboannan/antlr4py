"""Python target identifier escaping (ANTLR 4.13.2 reserved-word list).

Copyright (c) 2012-2017 The ANTLR Project. BSD-3-Clause, see LICENSE.txt.
"""
import keyword

RESERVED = frozenset('abs all and any apply as assert bin bool break buffer bytearray callable chr class classmethod coerce compile complex continue def del delattr dict dir divmod elif else enumerate eval execfile except file filter finally float for format from frozenset getattr global globals hasattr hash help hex id if import in input int intern is isinstance issubclass iter lambda len list locals map max min memoryview next nonlocal not object oct open or ord pass pow print property raise range raw_input reduce reload repr return reversed round set setattr slice sorted staticmethod str sum super try tuple type unichr unicode vars with while yield zip __import__ True False None rule parserRule state reset'.split()) | frozenset(keyword.kwlist)


def escaped(name):
    return name+'_' if name in RESERVED else name
