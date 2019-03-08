#!/usr/bin/env python

# Copyright (c) 2019, IRIS-HEP
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

import json

import numpy

import awkward.array.chunked
import awkward.array.indexed
import awkward.array.jagged
import awkward.array.masked
import awkward.array.objects
import awkward.array.table
import awkward.array.virtual
import awkward.type
import awkward.util

################################################################################ type conversions

def schema2type(schema):
    import pyarrow

    def recurse(tpe, nullable):
        if isinstance(tpe, pyarrow.lib.DictionaryType):
            out = recurse(tpe.dictionary.type, nullable)
            if nullable:
                return awkward.type.OptionType(out)
            else:
                return out

        elif isinstance(tpe, pyarrow.lib.StructType):
            out = None
            for i in range(tpe.num_children):
                x = awkward.type.ArrayType(tpe[i].name, recurse(tpe[i].type, tpe[i].nullable))
                if out is None:
                    out = x
                else:
                    out = out & x
            if nullable:
                return awkward.type.OptionType(out)
            else:
                return out

        elif isinstance(tpe, pyarrow.lib.ListType):
            out = awkward.type.ArrayType(float("inf"), recurse(tpe.value_type, nullable))
            if nullable:
                return awkward.type.OptionType(out)
            else:
                return out

        elif isinstance(tpe, pyarrow.lib.UnionType):
            out = None
            for i in range(tpe.num_children):
                x = recurse(tpe[i].type, nullable)
                if out is None:
                    out = x
                else:
                    out = out | x
            if nullable:
                return awkward.type.OptionType(out)
            else:
                return out

        elif tpe == pyarrow.string():
            if nullable:
                return awkward.type.OptionType(str)
            else:
                return str

        elif tpe == pyarrow.binary():
            if nullable:
                return awkward.type.OptionType(bytes)
            else:
                return bytes

        elif tpe == pyarrow.bool_():
            out = awkward.numpy.dtype(bool)
            if nullable:
                return awkward.type.OptionType(out)
            else:
                return out
            
        elif isinstance(tpe, pyarrow.lib.DataType):
            if nullable:
                return awkward.type.OptionType(tpe.to_pandas_dtype())
            else:
                return tpe.to_pandas_dtype()

        else:
            raise NotImplementedError(repr(tpe))

    out = None
    for name in schema.names:
        field = schema.field_by_name(name)
        mytype = awkward.type.ArrayType(name, recurse(field.type, field.nullable))
        if out is None:
            out = mytype
        else:
            out = out & mytype

    return out

################################################################################ value conversions

def toarrow(obj):
    import pyarrow

    def recurse(data, mask):
        if isinstance(data, numpy.ndarray):
            return pyarrow.array(data, mask=mask)

        elif isinstance(data, awkward.array.chunked.ChunkedArray):   # includes AppendableArray
            # TODO: I think Arrow has different chunking schemes, depending on whether this is
            #       just a column or a whole Arrow table/batch/thing.
            raise NotImplementedError("I'm putting off ChunkedArrays for now")

        elif isinstance(data, awkward.array.indexed.IndexedArray):
            if mask is None:
                return pyarrow.DictionaryArray.from_arrays(data.index, recurse(data.content, mask))
            else:
                return recurse(data.content[data.index], mask)

        elif isinstance(data, awkward.array.indexed.SparseArray):
            return recurse(data.dense, mask)

        elif isinstance(data, awkward.array.jagged.JaggedArray):
            data = data.compact()
            if mask is not None:
                mask = data._broadcast(mask).flatten()
            return pyarrow.ListArray.from_arrays(data.offsets, recurse(data.content, mask))

        elif isinstance(data, awkward.array.masked.MaskedArray):   # includes BitMaskedArray
            thismask = data.boolmask(maskedwhen=True)
            if mask is not None:
                thismask = mask & thismask
            return recurse(data.content, thismask)

        elif isinstance(data, awkward.array.masked.IndexedMaskedArray):
            thismask = data.boolmask(maskedwhen=True)
            if mask is not None:
                thismask = mask & thismask
            if len(data.content) == 0:
                content = data.numpy.empty(len(data.mask), dtype=data.DEFAULTTYPE)
            else:
                content = data.content[data.mask]
            return recurse(content, thismask)

        elif isinstance(data, awkward.array.objects.ObjectArray):
            # throw away Python object interpretation, which Arrow can't handle while being multilingual
            return recurse(data.content, mask)

        elif isinstance(data, awkward.array.objects.StringArray):
            # data = data.compact()
            raise NotImplementedError("I don't know how to make an Arrow StringArray")

            # I don't understand this
            # pyarrow.StringArray.from_buffers(2, pyarrow.py_buffer(numpy.array([0, 5, 10])), pyarrow.py_buffer(b"helloHELLO"), offset=0)
            # returns ["", "hello"]
            # ???

        elif isinstance(data, awkward.array.table.Table):
            return pyarrow.StructArray.from_arrays([recurse(x, mask) for x in data.contents.values()], list(data.contents))

        elif isinstance(data, awkward.array.union.UnionArray):
            contents = []
            for i, x in enumerate(data.contents):
                if mask is None:
                    thismask = None
                else:
                    thistags = (data.tags == i)
                    thismask = data.numpy.empty(len(x), dtype=data.MASKTYPE)
                    thismask[data.index[thistags]] = mask[thistags]    # hmm... data.index could have repeats; the Arrow mask in that case would not be well-defined...
                contents.append(recurse(x, thismask))

            return pyarrow.UnionArray.from_dense(pyarrow.array(data.tags.astype(numpy.int8)), pyarrow.array(data.index.astype(numpy.int32)), contents)

        elif isinstance(data, awkward.array.virtual.VirtualArray):
            return recurse(data.array, mask)

        else:
            raise TypeError("cannot convert type {0} to Arrow".format(type(data)))

    return recurse(obj, None)

def fromarrow(obj, awkwardlib=None):
    import pyarrow
    awkwardlib = awkward.util.awkwardlib(awkwardlib)
    ARROW_BITMASKTYPE = awkwardlib.numpy.uint8
    ARROW_INDEXTYPE = awkwardlib.numpy.int32
    ARROW_TAGTYPE = awkwardlib.numpy.uint8
    ARROW_CHARTYPE = awkwardlib.numpy.uint8

    def popbuffers(tpe, buffers):
        if isinstance(tpe, pyarrow.lib.DictionaryType):
            content = fromarrow(tpe.dictionary)
            index = popbuffers(tpe.index_type, buffers)
            if isinstance(index, awkwardlib.BitMaskedArray):
                return awkwardlib.BitMaskedArray(index.mask, awkwardlib.IndexedArray(index.content, content), maskedwhen=index.maskedwhen, lsborder=index.lsborder)
            else:
                return awkwardlib.IndexedArray(index, content)

        elif isinstance(tpe, pyarrow.lib.StructType):
            pairs = []
            for i in range(tpe.num_children - 1, -1, -1):
                pairs.insert(0, (tpe[i].name, popbuffers(tpe[i].type, buffers)))
            out = awkwardlib.Table.frompairs(pairs)
            mask = buffers.pop()
            if mask is not None:
                mask = awkwardlib.numpy.frombuffer(mask, dtype=ARROW_BITMASKTYPE)
                return awkwardlib.BitMaskedArray(mask, out, maskedwhen=False, lsborder=True)
            else:
                return out

        elif isinstance(tpe, pyarrow.lib.ListType):
            content = popbuffers(tpe.value_type, buffers)
            offsets = awkwardlib.numpy.frombuffer(buffers.pop(), dtype=ARROW_INDEXTYPE)
            out = awkwardlib.JaggedArray.fromoffsets(offsets, content)
            mask = buffers.pop()
            if mask is not None:
                mask = awkwardlib.numpy.frombuffer(mask, dtype=ARROW_BITMASKTYPE)
                return awkwardlib.BitMaskedArray(mask, out, maskedwhen=False, lsborder=True)
            else:
                return out

        elif isinstance(tpe, pyarrow.lib.UnionType) and tpe.mode == "sparse":
            contents = []
            for i in range(tpe.num_children - 1, -1, -1):
                contents.insert(0, popbuffers(tpe[i].type, buffers))
            assert buffers.pop() is None
            tags = awkwardlib.numpy.frombuffer(buffers.pop(), dtype=ARROW_TAGTYPE)
            index = awkwardlib.numpy.arange(len(tags), dtype=ARROW_INDEXTYPE)
            out = awkwardlib.UnionArray(tags, index, contents)
            mask = buffers.pop()
            if mask is not None:
                mask = awkwardlib.numpy.frombuffer(mask, dtype=ARROW_BITMASKTYPE)
                return awkwardlib.BitMaskedArray(mask, out, maskedwhen=False, lsborder=True)
            else:
                return out

        elif isinstance(tpe, pyarrow.lib.UnionType) and tpe.mode == "dense":
            contents = []
            for i in range(tpe.num_children - 1, -1, -1):
                contents.insert(0, popbuffers(tpe[i].type, buffers))
            index = awkwardlib.numpy.frombuffer(buffers.pop(), dtype=ARROW_INDEXTYPE)
            tags = awkwardlib.numpy.frombuffer(buffers.pop(), dtype=ARROW_TAGTYPE)
            out = awkwardlib.UnionArray(tags, index, contents)
            mask = buffers.pop()
            if mask is not None:
                mask = awkwardlib.numpy.frombuffer(mask, dtype=ARROW_BITMASKTYPE)
                return awkwardlib.BitMaskedArray(mask, out, maskedwhen=False, lsborder=True)
            else:
                return out

        elif tpe == pyarrow.string():
            content = awkwardlib.numpy.frombuffer(buffers.pop(), dtype=ARROW_CHARTYPE)
            offsets = awkwardlib.numpy.frombuffer(buffers.pop(), dtype=ARROW_INDEXTYPE)
            out = awkwardlib.StringArray.fromoffsets(offsets, content, encoding="utf-8")
            mask = buffers.pop()
            if mask is not None:
                mask = awkwardlib.numpy.frombuffer(mask, dtype=ARROW_BITMASKTYPE)
                return awkwardlib.BitMaskedArray(mask, out, maskedwhen=False, lsborder=True)
            else:
                return out

        elif tpe == pyarrow.binary():
            content = awkwardlib.numpy.frombuffer(buffers.pop(), dtype=ARROW_CHARTYPE)
            offsets = awkwardlib.numpy.frombuffer(buffers.pop(), dtype=ARROW_INDEXTYPE)
            out = awkwardlib.StringArray.fromoffsets(offsets, content, encoding=None)
            mask = buffers.pop()
            if mask is not None:
                mask = awkwardlib.numpy.frombuffer(mask, dtype=ARROW_BITMASKTYPE)
                return awkwardlib.BitMaskedArray(mask, out, maskedwhen=False, lsborder=True)
            else:
                return out

        elif tpe == pyarrow.bool_():
            out = awkwardlib.numpy.unpackbits(awkwardlib.numpy.frombuffer(buffers.pop(), dtype=ARROW_CHARTYPE)).view(awkwardlib.MaskedArray.BOOLTYPE)
            out = out.reshape(-1, 8)[:,::-1].reshape(-1)    # lsborder=True
            mask = buffers.pop()
            if mask is not None:
                mask = awkwardlib.numpy.frombuffer(mask, dtype=ARROW_BITMASKTYPE)
                return awkwardlib.BitMaskedArray(mask, out, maskedwhen=False, lsborder=True)
            else:
                return out

        elif isinstance(tpe, pyarrow.lib.DataType):
            out = awkwardlib.numpy.frombuffer(buffers.pop(), dtype=tpe.to_pandas_dtype())
            mask = buffers.pop()
            if mask is not None:
                mask = awkwardlib.numpy.frombuffer(mask, dtype=ARROW_BITMASKTYPE)
                return awkwardlib.BitMaskedArray(mask, out, maskedwhen=False, lsborder=True)
            else:
                return out

        else:
            raise NotImplementedError(repr(tpe))

    if isinstance(obj, pyarrow.lib.Array):
        buffers = obj.buffers()
        out = popbuffers(obj.type, buffers)[:len(obj)]
        assert len(buffers) == 0
        return out

    elif isinstance(obj, pyarrow.lib.ChunkedArray):
        chunks = [x for x in obj.chunks if len(x) > 0]
        if len(chunks) == 1:
            return chunks[0]
        else:
            return awkwardlib.ChunkedArray([fromarrow(x) for x in chunks], counts=[len(x) for x in chunks])

    elif isinstance(obj, pyarrow.lib.RecordBatch):
        out = awkwardlib.Table()
        for n, x in zip(obj.schema.names, obj.columns):
            out[n] = fromarrow(x)
        return out

    elif isinstance(obj, pyarrow.lib.Table):
        chunks = []
        counts = []
        for batch in obj.to_batches():
            chunk = fromarrow(batch)
            if len(chunk) > 0:
                chunks.append(chunk)
                counts.append(len(chunk))
        if len(chunks) == 1:
            return chunks[0]
        else:
            return awkwardlib.ChunkedArray(chunks, counts=counts)

    else:
        raise NotImplementedError(type(obj))

################################################################################ Parquet file handling

def toparquet(obj):
    raise NotImplementedError

class _ParquetFile(object):
    def __init__(self, file, cache=None, metadata=None, common_metadata=None):
        self.file = file
        self.cache = cache
        self.metadata = metadata
        self.common_metadata = common_metadata
        self._init()

    def _init(self):
        import pyarrow.parquet
        self.parquetfile = pyarrow.parquet.ParquetFile(self.file, metadata=self.metadata, common_metadata=self.common_metadata)
        self.type = schema2type(self.parquetfile.schema.to_arrow_schema())
        
    def __getstate__(self):
        return {"file": self.file, "metadata": self.metadata, "common_metadata": self.common_metadata}

    def __setstate__(self, state):
        self.file = state["file"]
        self.cache = None
        self.metadata = state["metadata"]
        self.common_metadata = state["common_metadata"]
        self._init()

    def __call__(self, rowgroup, column):
        return fromarrow(self.parquetfile.read_row_group(rowgroup, columns=[column]))[column]

    def tojson(self):
        json.dumps([self.file, self.metadata, self.common_metadata])
        return {"file": self.file, "metadata": self.metadata, "common_metadata": self.common_metadata}

    @classmethod
    def fromjson(cls, state):
        return cls(state["file"], cache=None, metadata=state["metadata"], common_metadata=state["common_metadata"])

def fromparquet(file, awkwardlib=None, cache=None, persistvirtual=False, metadata=None, common_metadata=None):
    awkwardlib = awkward.util.awkwardlib(awkwardlib)
    parquetfile = _ParquetFile(file, cache=cache, metadata=metadata, common_metadata=common_metadata)
    columns = parquetfile.type.columns

    chunks = []
    counts = []
    for i in range(parquetfile.parquetfile.num_row_groups):
        numrows = parquetfile.parquetfile.metadata.row_group(i).num_rows
        if numrows > 0:
            chunk = awkwardlib.Table()
            for n in columns:
                chunk[n] = awkwardlib.VirtualArray(parquetfile, (i, n), cache=cache, type=awkwardlib.type.ArrayType(numrows, parquetfile.type[n]), persistvirtual=persistvirtual)
            chunks.append(chunk)
            counts.append(numrows)

    return awkwardlib.ChunkedArray(chunks, counts)
