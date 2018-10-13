#!/usr/bin/env python

# Copyright (c) 2018, DIANA-HEP
# All rights reserved.
# 
# Redistribution and use in source and binary forms, with or without
# modification, are permitted provided that the following conditions are met:
# 
# * Redistributions of source code must retain the above copyright notice, this
#   list of conditions and the following disclaimer.
# 
# * Redistributions in binary form must reproduce the above copyright notice,
#   this list of conditions and the following disclaimer in the documentation
#   and/or other materials provided with the distribution.
# 
# * Neither the name of the copyright holder nor the names of its
#   contributors may be used to endorse or promote products derived from
#   this software without specific prior written permission.
# 
# THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS "AS IS"
# AND ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT LIMITED TO, THE
# IMPLIED WARRANTIES OF MERCHANTABILITY AND FITNESS FOR A PARTICULAR PURPOSE ARE
# DISCLAIMED. IN NO EVENT SHALL THE COPYRIGHT HOLDER OR CONTRIBUTORS BE LIABLE
# FOR ANY DIRECT, INDIRECT, INCIDENTAL, SPECIAL, EXEMPLARY, OR CONSEQUENTIAL
# DAMAGES (INCLUDING, BUT NOT LIMITED TO, PROCUREMENT OF SUBSTITUTE GOODS OR
# SERVICES; LOSS OF USE, DATA, OR PROFITS; OR BUSINESS INTERRUPTION) HOWEVER
# CAUSED AND ON ANY THEORY OF LIABILITY, WHETHER IN CONTRACT, STRICT LIABILITY,
# OR TORT (INCLUDING NEGLIGENCE OR OTHERWISE) ARISING IN ANY WAY OUT OF THE USE
# OF THIS SOFTWARE, EVEN IF ADVISED OF THE POSSIBILITY OF SUCH DAMAGE.

import importlib
import json
import numbers
import zlib

import numpy

import awkward.util
import awkward.version

contexts = ("ChunkedArray.chunks",
            "AppendableArray.chunks",
            "IndexedArray.index",
            "IndexedArray.content",
            "ByteIndexedArray.index",
            "ByteIndexedArray.content",
            "SparseArray.index",
            "SparseArray.content",
            "JaggedArray.counts",
            "JaggedArray.starts",
            "JaggedArray.stops",
            "JaggedArray.content",
            "ByteJaggedArray.counts",
            "ByteJaggedArray.starts",
            "ByteJaggedArray.stops",
            "ByteJaggedArray.content",
            "MaskedArray.mask",
            "MaskedArray.content",
            "BitMaskedArray.mask",
            "BitMaskedArray.content",
            "IndexedMaskedArray.mask",
            "IndexedMaskedArray.content",
            "ObjectArray.content",
            "Table.content",
            "UnionArray.tags",
            "UnionArray.index",
            "UnionArray.content",
            "VirtualArray.setitem")

compression = [
    [8192, [numpy.bool_, numpy.bool, numpy.integer], list(contexts), (zlib.compress, ("zlib", "decompress"))],
    ]

def dtype2json(obj):
    if obj.subdtype is not None:
        dt, sh = obj.subdtype
        return (dtype2json(dt), sh)
    elif obj.names is not None:
        return [(n, dtype2json(obj[n])) for n in obj.names]
    else:
        return str(obj)

def json2dtype(obj):
    def recurse(obj):
        if isinstance(obj, (list, tuple)) and len(obj) > 0 and (isinstance(obj[-1], numbers.Integral) or isinstance(obj[0], str) or (isinstance(obj[-1], (list, tuple)) and all(isinstance(x, numbers.Integral) for x in obj[-1]))):
            return tuple(recurse(x) for x in obj)
        elif isinstance(obj, (list, tuple)):
            return [recurse(x) for x in obj]
        else:
            return obj
    return numpy.dtype(recurse(obj))

def serialize(obj, sink, prefix="", compression=compression):
    import awkward.array.base

    if isinstance(compression, tuple) and len(compression) == 2 and callable(compression[0]):
        compression = [(0, (object,), contexts, (zlib.compress, ("zlib", "decompress")))]

    seen = {}
    def fill(obj, context):
        if id(obj) in seen:
            return {"ref": seen[id(obj)]}

        ident = len(seen)
        seen[id(obj)] = ident

        if type(obj) is numpy.ndarray and len(obj.shape) != 0:
            if len(obj.shape) > 1:
                dtype = dtype2json(numpy.dtype((obj.dtype, obj.shape[1:])))
            else:
                dtype = dtype2json(obj.dtype)

            for minsize, types, contexts, pair in compression:
                if obj.nbytes >= minsize and issubclass(obj.dtype.type, tuple(types)) and context in contexts:
                    compress, decompress = pair
                    sink[prefix + str(ident)] = compress(obj)

                    return {"id": ident,
                            "gen": ["numpy", "frombuffer"],
                            "args": [{"gen": decompress, "args": [{"read": str(ident)}]},
                                     {"gen": ["awkward.persist", "json2dtype"], [dtype]},
                                     len(obj)]}

            else:
                sink[prefix + str(ident)] = obj.tostring()
                return {"id": ident,
                        "gen": ["numpy", "frombuffer"],
                        "args": [{"read": str(ident)},
                                 {"gen": ["awkward.persist", "json2dtype"], [dtype]},
                                 len(obj)]}

        elif hasattr(obj, "__awkward_persist__"):
            return obj.__awkward_persist__(ident, fill, sink)

        else:
            raise TypeError("cannot serialize {0} instance (has no __awkward_persist__ method)".format(type(obj)))

    schema = {"awkward": awkward.version.__version__,
              "prefix": prefix,
              "schema": fill(obj, None)}

    sink[prefix] = json.dumps(schema).encode("ascii")
    return schema

whitelist = [["numpy", "frombuffer"], ["zlib", "decompress"], ["awkward", "*"], ["awkward.persist", "*"]]

def deserialize(source, prefix="", whitelist=whitelist):
    schema = json.loads(schema)
    prefix = schema["prefix"]
    seen = {}

    def unfill(schema):
        if isinstance(schema, dict):
            if hasattr(schema, "gen"):
                gen, genname = importlib.import_module(schema[0]), schema[1:]
                while len(genname) > 0:
                    gen, genname = getattr(gen, genname[0]), genname[1:]

                args = [unfill(x) for x in schema.get("args", [])]

                out = gen(*args)
                if "id" in schema:
                    seen[schema["id"]] = out
                return out
                
            elif hasattr(schema, "read"):
                if schema.get("absolute", False):
                    return source[schema["read"]]
                else:
                    return source[prefix + schema["read"]]
                
            elif hasattr(schema, "ref"):
                return seen[schema["ref"]]

            else:
                return schema

        else:
            return schema

    return unfill(schema["schema"])







            
# class Ident(object):
#     __slots__ = ("_i",)

#     def __init__(self, obj):
#         self._i = id(obj)

#     def __repr__(self):
#         return "<Ident {0}>".format(self._i)

#     def __hash__(self):
#         return hash((Ident, self._i))

#     def __eq__(self, other):
#         return isinstance(other, Ident) and self._i == other._i

#     def __ne__(self, other):
#         return not self.__eq__(other)

# class State(object):
#     __slots__ = ("ident", "decompress", "create", "compressed", "uncompressed")

#     def __init__(self, ident, decompress, create, compressed, uncompressed):
#         self.ident = ident
#         self.decompress = decompress
#         self.create = create
#         self.compressed = compressed
#         self.uncompressed = uncompressed

#     def __repr__(self):
#         return "<State {0} {1} {2} {3} {4}>".format(self.ident, self.decompress, self.create, self.compressed, self.uncompressed)

#     def __hash__(self):
#         return hash((State, self.ident, self.decompress, self.create, tuple((n, self.compressed[n]) for n in sorted(self.compressed)), tuple((n, self.uncompressed[n]) for n in sorted(self.uncompressed))))

#     def __eq__(self, other):
#         return isinstance(other, State) and self.ident == other.ident and self.decompress == other.decompress and self.create == other.create and self.compressed == other.compressed and self.uncompressed == other.uncompressed

#     def __ne__(self, other):
#         return not self.__eq__(other)

#     def fromstate(self, seen):
#         if self.decompress is None:
#             decompress = lambda x: x
#         else:
#             decompress, decompressname = importlib.import_module(self.decompress[0]), self.decompress[1:]
#             while len(decompressname) > 0:
#                 decompress, decompressname = getattr(decompress, decompressname[0]), decompressname[1:]

#         create, createname = importlib.import_module(self.create[0]), self.create[1:]
#         while len(createname) > 0:
#             create, createname = getattr(create, createname[0]), createname[1:]

#         kwargs = {}
#         for n, x in self.compressed.items():
#             kwargs[n] = decompress(x)

#         for n, x in self.uncompressed.items():
#             if isinstance(x, State):
#                 kwargs[n] = fromstate(x, seen)
#             else:
#                 kwargs[n] = x

#         return create(**kwargs)
        
# def tostate(obj, context, seen):
#     import awkward.array.base

#     ident = Ident(obj)
#     if ident in seen:
#         return ident

#     elif type(obj) is numpy.ndarray and len(obj.shape) != 0:
#         for minsize, types, contexts, pair in compressor:
#             if obj.nbytes >= minsize and issubclass(obj.dtype.type, tuple(types)) and context in contexts:
#                 compress, decompress = pair

#                 if len(obj.shape) == 1:
#                     dtype = obj.dtype
#                 else:
#                     dtype = numpy.dtype((obj.dtype, obj.shape[1:]))

#                 create = ("numpy", "frombuffer")
#                 compressed = {"buffer": compress(obj)}
#                 uncompressed = {"dtype": dtype, "count": len(obj), "offset": 0}
                    
#                 seen.add(ident)
#                 return State(ident, decompress, create, compressed, uncompressed)

#         else:
#             return obj

#     elif isinstance(obj, awkward.array.base.AwkwardArray):
#         seen.add(ident)
#         return obj._tostate(seen)

#     else:
#         return obj

# def fromstate(state, seen):
#     import awkward.array.base

#     if isinstance(state, Ident):
#         return seen[state]

#     elif isinstance(state, State):
#         out = state.fromstate(seen)
#         seen[state.ident] = out
#         return out

#     else:
#         return state
