# %%markdown
# # Introduction
#
# Numpy is great for exploratory data analysis because it encourages the analyst to calculate one operation at a time, rather than one datum at a time. To compute an expression like
#
# .. math::
#
#     m = \\sqrt{(E_1 + E_2)^2 - (p_{x1} + p_{x2})^2 - (p_{y1} + p_{y2})^2 - (p_{z1} + p_{z2})^2}
#
# you might first compute :math:`\\sqrt{(p_{x1} + p_{x2})^2 + (p_{y1} + p_{y2})^2}` for all data (which is a meaningful quantity: :math:`p_T`), then compute :math:`\\sqrt{{p_T}^2 + (p_{z1} + p_{z2})^2}` for all data (another meaningful quantity: :math:`|p|`), then compute the whole expression as :math:`\\sqrt{(E_1 + E_2)^2 - |p|^2}`. Performing each step separately on all data lets you plot and cross-check distributions of partial computations, to discover surprises as early as possible.
#
# This order of data processing is called "columnar" in the sense that a dataset may be visualized as a table in which rows are repeated measurements and columns are the different measurable quantities (same layout as `Pandas DataFrames <https://pandas.pydata.org>`__). It is also called "vectorized" in that a Single (virtual) Instruction is applied to Multiple Data (virtual SIMD). Numpy can be hundreds to thousands of times faster than pure Python because it avoids the overhead of handling Python instructions in the loop over numbers. Most data processing languages (R, MATLAB, IDL, all the way back to APL) work this way: an interactive interpreter controlling fast, array-at-a-time math.
#
# However, it's difficult to apply this methodology to non-rectangular data. If your dataset has nested structure, a different number of values per row, different data types in the same column, or cross-references or even circular references, Numpy can't help you.
#
# If you try to make an array with non-trivial types:

# %%
import numpy
nested = numpy.array([{"x": 1, "y": 1.1}, {"x": 2, "y": 2.2}, {"x": 3, "y": 3.3}, {"x": 4, "y": 4.4}, {"x": 5, "y": 5.5}])
nested

# %%markdown
# Numpy gives up and returns a ``dtype=object`` array, which means Python objects and pure Python processing. You don't get the columnar operations or the performance boost.
#
# For instance, you might want to say

# %%
try:
    nested + 100
except Exception as err:
    print(type(err), str(err))

# %%markdown
# but there is no vectorized addition for an array of dicts because there is no addition for dicts defined in pure Python. Numpy is not using its vectorized routines—it's calling Python code on each element.
#
# The same applies to variable-length data, such as lists of lists, where the inner lists have different lengths. This is a more serious shortcoming than the above because the list of dicts (Python's equivalent of an "`array of structs <https://en.wikipedia.org/wiki/AOS_and_SOA>`__`") could be manually reorganized into two numerical arrays, ``"x"`` and ``"y"`` (a "`struct of arrays <https://en.wikipedia.org/wiki/AOS_and_SOA>`__"). Not so with a list of variable-length lists.

# %%
varlen = numpy.array([[1.1, 2.2, 3.3], [], [4.4, 5.5], [6.6], [7.7, 8.8, 9.9]])
varlen

# %%markdown
# As before, we get a ``dtype=object`` without vectorized methods.

# %%
try:
    varlen + 100
except Exception as err:
    print(type(err), str(err))

# %%markdown
# What's worse, this array looks purely numerical and could have been made by a process that was *supposed* to create equal-length inner lists.
#
# Awkward-array provides a way of talking about these data structures as arrays.

# %%
import awkward
nested = awkward.fromiter([{"x": 1, "y": 1.1}, {"x": 2, "y": 2.2}, {"x": 3, "y": 3.3}, {"x": 4, "y": 4.4}, {"x": 5, "y": 5.5}])
nested

# %%markdown
# This ``Table`` is a columnar data structure with the same meaning as the Python data we built it with. To undo ``awkward.fromiter``, call ``.tolist()``.

# %%
nested.tolist()

# %%markdown
# Values at the same position of the tree structure are contiguous in memory: this is a struct of arrays.

# %%
nested.contents["x"]

# %%
nested.contents["y"]

# %%markdown
# Having a structure like this means that we can perform vectorized operations on the whole structure with relatively few Python instructions (number of Python instructions scales with the complexity of the data type, not with the number of values in the dataset).

# %%
(nested + 100).tolist()

# %%
(nested + numpy.arange(100, 600, 100)).tolist()

# %%markdown
# It's less obvious that variable-length data can be represented in a columnar format, but it can.

# %%
varlen = awkward.fromiter([[1.1, 2.2, 3.3], [], [4.4, 5.5], [6.6], [7.7, 8.8, 9.9]])
varlen

# %%markdown
# Unlike Numpy's ``dtype=object`` array, the inner lists are *not* Python lists and the numerical values *are* contiguous in memory. This is made possible by representing the structure (where each inner list starts and stops) in one array and the values in another.

# %%
varlen.counts, varlen.content

# %%markdown
# (For fast random access, the more basic representation is ``varlen.offsets``, which is in turn a special case of a ``varlen.starts, varlen.stops`` pair. These details are discussed below.)
#
# A structure like this can be broadcast like Numpy with a small number of Python instructions (scales with the complexity of the data type, not the number of values).

# %%
varlen + 100

# %%
varlen + numpy.arange(100, 600, 100)

# %%markdown
# You can even slice this object as though it were multidimensional (each element is a tensor of the same rank, but with different numbers of dimensions).

# %%
# Skip the first two inner lists; skip the last value in each inner list that remains.
varlen[2:, :-1]

# %%markdown
# The data are not rectangular, so some inner lists might have as many elements as your selection. Don't worry—you'll get error messages.

# %%
try:
    varlen[:, 1]
except Exception as err:
    print(type(err), str(err))

# %%markdown
# Masking with the ``.counts`` is handy because all the Numpy advanced indexing rules apply (in an extended sense) to jagged arrays.

# %%
varlen[varlen.counts > 1, 1]

# %%markdown
# I've only presented the two most important awkward classes, ``Table`` and ``JaggedArray`` (and not how they combine). Each class is presented in more detail below. For now, I'd just like to point out that you can make crazy complicated data structures

# %%
crazy = awkward.fromiter([[1.21, 4.84, None, 10.89, None],
                          [19.36, [30.25]],
                          [{"x": 36, "y": {"z": 49}}, None, {"x": 64, "y": {"z": 81}}]
                         ])

# %%markdown
# and they vectorize and slice as expected.

# %%
numpy.sqrt(crazy).tolist()

# %%markdown
# This is because any awkward array can be the content of any other awkward array. Like Numpy, the features of awkward-array are simple, yet compose nicely to let you build what you need.

# %%markdown
# # Overview with sample datasets
#
# Many of the examples in this tutorial use ``awkward.fromiter`` to make awkward arrays from lists and ``array.tolist()`` to turn them back into lists (or dicts for ``Table``, tuples for ``Table`` with anonymous fields, Python objects for ``ObjectArrays``, etc.). These should be considered slow methods, since Python instructions are executed in the loop, but that's a necessary part of examining or building Python objects.
#
# Ideally, you'd want to get your data from a binary, columnar source and produce binary, columnar output, or convert only once and reuse the converted data. `Parquet <https://parquet.apache.org>`__ is a popular columnar format for storing data on disk and `Arrow <https://arrow.apache.org>`__ is a popular columnar format for sharing data in memory (between functions or applications). `ROOT <https://root.cern>`__ is a popular columnar format for particle physicists, and `uproot <https://github.com/scikit-hep/uproot>`__ natively produces awkward arrays from ROOT files.
#
# `HDF5 <https://www.hdfgroup.org>`__ and its Python library `h5py <https://www.h5py.org/>`__ are columnar, but only for rectangular arrays, unlike the others mentioned here. Awkward-array can *wrap* HDF5 with an interpretation layer to store columnar data structures, but then the awkward-array library wuold be needed to read the data back in a meaningful way. Awkward also has a native file format, ``.awkd`` files, which are simply ZIP archives of columns as binary blobs and metadata (just as Numpy's ``.npz`` is a ZIP of arrays with metadata). The HDF5, awkd, and pickle serialization procedures use the same protocol, which has backward and forward compatibility features.

# %%markdown
# ## NASA exoplanets from a Parquet file
#
# Let's start by opening a Parquet file. Awkward reads Parquet through the `pyarrow <https://arrow.apache.org/docs/python>`__ module, which is an optional dependency, so be sure you have it installed before trying the next line.

# %%
stars = awkward.fromparquet("tests/samples/exoplanets.parquet")
stars

# %%markdown
# (There is also an ``awkward.toparquet`` that takes the file name and array as arguments.)
#
# Columns are accessible with square brackets and strings

# %%
stars["name"]

# %%markdown
# or by dot-attribute (if the name doesn't have weird characters and doesn't conflict with a method or property name).

# %%
stars.ra, stars.dec

# %%markdown
# This file contains data about extrasolar planets and their host stars. As such, it's a ``Table`` full of Numpy arrays and ``JaggedArrays``. The star attributes (`"name"`, `"ra"` or right ascension in degrees, `"dec"` or declination in degrees, `"dist"` or distance in parsecs, `"mass"` in multiples of the sun's mass, and `"radius"` in multiples of the sun's radius) are plain Numpy arrays and the planet attributes (`"name"`, `"orbit"` or orbital distance in AU, `"eccen"` or eccentricity, `"period"` or periodicity in days, `"mass"` in multiples of Jupyter's mass, and `"radius"` in multiples of Jupiter's radius) are jagged because each star may have a different number of planets.

# %%
stars.planet_name

# %%
stars.planet_period, stars.planet_orbit

# %%markdown
# For large arrays, only the first and last values are printed: the second-to-last star has three planets; all the other stars shown here have one planet.
#
# These arrays are called ``ChunkedArrays`` because the Parquet file is lazily read in chunks (Parquet's row group structure). The ``ChunkedArray`` (subdivides the file) contains ``VirtualArrays`` (read one chunk on demand), which generate the ``JaggedArrays``. This is an illustration of how each awkward class provides one feature, and you get desired behavior by combining them.
#
# The ``ChunkedArrays`` and ``VirtualArrays`` support the same Numpy-like access as ``JaggedArray``, so we can compute with them just as we would any other array.

# %%
# distance in parsecs → distance in light years
stars.dist * 3.26156

# %%
# for all stars, drop the first planet
stars.planet_mass[:, 1:]

# %%markdown
# ## NASA exoplanets from an Arrow buffer
#
# The pyarrow implementation of Arrow is more complete than its implementation of Parquet, so we can use more features in the Arrow format, such as nested tables.
#
# Unlike Parquet, which is intended as a file format, Arrow is a memory format. You might get an Arrow buffer as the output of another function, through interprocess communication, from a network RPC call, a message bus, etc. Arrow can be saved as files, though this isn't common. In this case, we'll get it from a file.

# %%
import pyarrow
arrow_buffer = pyarrow.ipc.open_file(open("tests/samples/exoplanets.arrow", "rb")).get_batch(0)
stars = awkward.fromarrow(arrow_buffer)
stars

# %%markdown
# (There is also an ``uproot.toarrow`` that takes an awkward array as its only argument, returning the relevant Arrow structure.)
#
# This file is structured differently. Instead of jagged arrays of numbers like ``"planet_mass"``, ``"planet_period"``, and ``"planet_orbit"``, this file has a jagged table of ``"planets"``. A jagged table is a ``JaggedArray`` of ``Table``.

# %%
stars["planets"]

# %%markdown
# Notice that the square brackets are nested, but the contents are ``<Row>`` objects. The second-to-last star has three planets, as before.
#
# We can find the non-jagged ``Table`` in the ``JaggedArray.content``.

# %%
stars["planets"].content

# %%markdown
# When viewed as Python lists and dicts, the ``'planets'`` field is a list of planet dicts, each with its own fields.

# %%
stars[:2].tolist()

# %%markdown
# Despite being packaged in an arguably more intuitive way, we can still get jagged arrays of numbers by requesting ``"planets"`` and a planet attribute (two column selections) without specifying which star or which parent.

# %%
stars.planets.name

# %%
stars.planets.mass

# %%markdown
# Even though the ``Table`` is hidden inside the ``JaggedArray``, its ``columns`` pass through to the top.

# %%
stars.columns

# %%
stars.planets.columns

# %%markdown
# For a more global view of the structures contained within one of these arrays, print out its high-level type. ("High-level" because it presents logical distinctions, like jaggedness and tables, but not physical distinctions, like chunking and virtualness.)

# %%
print(stars.type)

# %%markdown
# The above should be read like a function's data type: ``argument type -> return type`` for the function that takes an index in square brackets and returns something else. For example, the first ``[0, 2935)`` means that you could put any non-negative integer less than ``2935`` in square brackets after ``stars``, like this:

# %%
stars[1734]

# %%markdown
# and get an object that would take ``'dec'``, ``'dist'``, ``'mass'``, ``'name'``, ``'planets'``, ``'ra'``, or ``'radius'`` in its square brackets. The return type depends on which of those strings you provide.

# %%
stars[1734]["mass"]   # type is float64

# %%
stars[1734]["name"]   # type is <class 'str'>

# %%
stars[1734]["planets"]

# %%markdown
# The planets have their own table structure:

# %%
print(stars[1734]["planets"].type)

# %%markdown
# Notice that within the context of ``stars``, the ``planets`` could take any non-negative integer ``[0, inf)``, but for a particular star, the allowed domain is known with more precision: ``[0, 5)``. This is because ``stars["planets"]`` is a jagged array—a different number of planets for each star—but one ``stars[1734]["planets"]`` is a simple array—five planets for *this* star.
#
# Passing a non-negative integer less than 5 to this array, we get an object that takes one of six strings: : ``'eccen'``, ``'mass'``, ``'name'``, ``'orbit'``, ``'period'``, and ``'radius'``.

# %%
stars[1734]["planets"][4]

# %%markdown
# and the return type of these depends on which string you provide.

# %%
stars[1734]["planets"][4]["period"]   # type is float

# %%
stars[1734]["planets"][4]["name"]   # type is <class 'str'>

# %%
stars[1734]["planets"][4].tolist()

# %%markdown
# (Incidentally, this is a `potentially habitable exoplanet <https://www.nasa.gov/ames/kepler/kepler-186f-the-first-earth-size-planet-in-the-habitable-zone>`__`, the first ever discovered.)

# %%
stars[1734]["name"], stars[1734]["planets"][4]["name"]

# %%markdown
# Some of these arguments "commute" and others don't. Dimensional axes have a particular order, so you can't request a planet by its row number before selecting a star, but you can swap a column-selection (string) and a row-selection (integer). For a rectangular table, it's easy to see how you can slice column-first or row-first, but it even works when the table is jagged.

# %%
stars["planets"]["name"][1734][4]

# %%
stars[1734]["planets"][4]["name"]

# %%markdown
# None of these intermediate slices actually process data, so you can slice in any order that is logically correct without worrying about performance. Projections, even multi-column projections

# %%
orbits = stars["planets"][["name", "eccen", "orbit", "period"]]
orbits[1734].tolist()

# %%markdown
# are a useful way to restructure data without incurring a runtime cost.

# %%markdown
# ## Relationship to Pandas
#
# Arguably, this kind of dataset could be manipulated as a `Pandas DataFrame <https://pandas.pydata.org>`__ instead of awkward arrays. Despite the variable number of planets per star, the exoplanets dataset could be flattened into a rectangular DataFrame, in which the distinction between solar systems is represented by a two-component index (leftmost pair of columns below), a `MultiIndex <https://pandas.pydata.org/pandas-docs/stable/user_guide/advanced.html>`__.

# %%
awkward.topandas(stars, flatten=True)[-9:]

# %%markdown
# In this representation, each star's attributes must be duplicated for all of its planets, and it is not possible to show stars that have no planets (not present in this dataset), but the information is preserved in a way that Pandas can recognize and operate on. (For instance, ``.unstack()`` would widen each planet attribute into a separate column per planet and simplify the index to strictly one row per star.)
#
# The limitation is that only a single jagged structure can be represented by a DataFrame. The structure can be arbitrarily deep in ``Tables`` (which add depth to the column names),

# %%
array = awkward.fromiter([{"a": {"b": 1, "c": {"d": [2]}}, "e": 3},
                          {"a": {"b": 4, "c": {"d": [5, 5.1]}}, "e": 6},
                          {"a": {"b": 7, "c": {"d": [8, 8.1, 8.2]}}, "e": 9}])
awkward.topandas(array, flatten=True)

# %%markdown
# and arbitrarily deep in ``JaggedArrays`` (which add depth to the row names),

# %%
array = awkward.fromiter([{"a": 1, "b": [[2.2, 3.3, 4.4], [], [5.5, 6.6]]},
                          {"a": 10, "b": [[1.1], [2.2, 3.3], [], [4.4]]},
                          {"a": 100, "b": [[], [9.9]]}])
awkward.topandas(array, flatten=True)

# %%markdown
# and they can even have two ``JaggedArrays`` at the same level if their number of elements is the same (at all levels of depth).

# %%
array = awkward.fromiter([{"a": [[1.1, 2.2, 3.3], [], [4.4, 5.5]], "b": [[1, 2, 3], [], [4, 5]]},
                          {"a": [[1.1], [2.2, 3.3], [], [4.4]],    "b": [[1], [2, 3], [], [4]]},
                          {"a": [[], [9.9]],                       "b": [[], [9]]}])
awkward.topandas(array, flatten=True)

# %%markdown
# But if there are two ``JaggedArrays`` with *different* structure at the same level, a single DataFrame cannot represent them.

# %%
array = awkward.fromiter([{"a": [1, 2, 3], "b": [1.1, 2.2]},
                          {"a": [1],       "b": [1.1, 2.2, 3.3]},
                          {"a": [1, 2],    "b": []}])
try:
    awkward.topandas(array, flatten=True)
except Exception as err:
    print(type(err), str(err))

# %%markdown
# To describe data like these, you'd need two DataFrames, and any calculations involving both ``"a"`` and ``"b"`` would have to include a join on those DataFrames. Awkward arrays are not limited in this way: the last ``array`` above is a valid awkward array and is useful for calculations that mix ``"a"`` and ``"b"``.

# %%markdown
# ## LHC data from a ROOT file
#
# Particle physicsts need structures like these—in fact, they have been a staple of particle physics analyses for decades. The `ROOT <https://root.cern>`__ file format was developed in the mid-90's to serialize arbitrary C++ data structures in a columnar way (replacing ZEBRA and similar Fortran projects that date back to the 70's). The `PyROOT <https://root.cern.ch/pyroot>`__ library dynamically wraps these objects to present them in Python, though with a performance penalty. The `uproot <https://github.com/scikit-hep/uproot>`__ library reads columnar data directly from ROOT files in Python without intermediary C++.

# %%
import uproot
events = uproot.open("http://scikit-hep.org/uproot/examples/HZZ-objects.root")["events"].lazyarrays()
events

# %%
events.columns

# %%markdown
# This is a typical particle physics dataset (though small!) in that it represents the momentum and energy (``"p4"`` for `Lorentz 4-momentum <https://en.wikipedia.org/wiki/Four-vector`__) of several different species of particles: ``"jet"``, ``"muon"``, ``"electron"``, and ``"photon"``. Each collision can produce a different number of particles in each species. Other variables, such as missing transverse energy or ``"MET"``, have one value per collision event. Events with zero particles in a species are valuable for the event-level data.

# %%
# The first event has two muons.
events.muonp4

# %%
# The first event has zero jets.
events.jetp4

# %%
# Every event has exactly one MET.
events.MET

# %%markdown
# Unlike the exoplanet data, these events cannot be represented as a DataFrame because of the different numbers of particles in each species and because zero-particle events have value. Even with just ``"muonp4"``, ``"jetp4"``, and ``"MET"``, there is no translation.

# %%
try:
    awkward.topandas(events[["muonp4", "jetp4", "MET"]], flatten=True)
except Exception as err:
    print(type(err), str(err))

# %%markdown
# It could be described as a collection of DataFrames, in which every operation relating particles in the same event would require a join. But that would make analysis harder, not easier. An event has meaning on its own.

# %%
events[0].tolist()

# %%markdown
# Particle physics isn't alone in this: analyzing JSON-formatted log files in production systems or allele likelihoods in genomics are two other fields where variable-length, nested structures can help. Arbitrary data structures are useful and working with them in columns provides a new way to do exploratory data analysis: one array at a time.

# %%markdown
# # Awkward-array scope
#
# Awkward array features are provided by a suite of classes that each extend Numpy arrays in one small way. These classes may then be composed to combine features.
#
# In this sense, Numpy arrays are awkward-array's most basic array class. A Numpy array is a small Python object that points to a large, contiguous region of memory, and, as much as possible, operations on that array replace the Pythonic interpretation, not the data themselves. Therefore, many Numpy operations are *views*, rather than *in-place operations* or *copies*, leaving the original value intact but returning a new value that is linked with the original. Assigning to arrays and in-place operations are allowed, but they add complexity because one must be aware of which arrays are views and which are copies.
#
# Awkward-array's model is to treat all arrays as though they were immutable, favoring views over copies, and not providing any high-level in-place operations on array data. (In other words, awkward arrays have no square-bracket assignment, ``__setitem__``, though the Pythonic interpretation objects can be changed in-place.)
#
# A Numpy array has a `dtype <https://docs.scipy.org/doc/numpy/reference/arrays.dtypes.html>`__ to interpret bytes as signed and unsigned integers of various bit-widths, floating-point numbers, booleans, little endian and big endian, fixed-width bytestrings (for applications such as 6-byte MAC addresses or human-readable strings with padding), or `record arrays <https://docs.scipy.org/doc/numpy/user/basics.rec.html>`__ for contiguous structures. (Awkward-array's ``Table`` has the same interface as Numpy record arrays, except that fields are not required to be contiguous in memory.) A Numpy array has a `pointer <https://docs.scipy.org/doc/numpy/reference/generated/numpy.ndarray.ctypes.html>`__ to the first element of its data buffer (``array.ctypes.data``) and a `shape <https://docs.scipy.org/doc/numpy/reference/generated/numpy.ndarray.shape.html>`__ to describe its ``N`` lengths as a rank-``N`` tensor. Only the first of these lengths is the length as returned by the Python function ``len``. Furthermore, an `order <https://docs.scipy.org/doc/numpy/reference/generated/numpy.ndarray.flags.html>`__ flag determines if rank > 1 arrays are laid out in "C" order or "Fortran" order. A Numpy array also has a `stride <https://docs.scipy.org/doc/numpy/reference/generated/numpy.ndarray.strides.html>`__` to determine how many bytes separate one element from the next. (Data in a Numpy array need not be strictly contiguous, but they must be regular: the number of bytes seprating them is a constant.) This stride may even be negative to describe a reversed view of an array, which allows any ``slice`` of an array, even those with ``skip != 1`` to be a view, rather than a copy. Numpy arrays also have flags to determine whether they `own <https://docs.scipy.org/doc/numpy/reference/generated/numpy.ndarray.flags.html>`__` their data buffer (and should therefore delete it when the Python object goes out of scope) and whether the data buffer is `writable <https://docs.scipy.org/doc/numpy/reference/generated/numpy.ndarray.flags.html>`__.
#
# 





# %%markdown
# # High-level operations: common to all types



# %%markdown
# ## Slicing with square brackets

# %%markdown
# ## Assigning with square brackets

# %%markdown
# ## Numpy universal functions and broadcasting

# %%markdown
# ## Reducers

# %%markdown
# ## Jagged properties and methods

# %%markdown
# ## Tabular properties and methods

# %%markdown
# ## Nullable properties and methods

# %%markdown
# # High-level types

# %%markdown
# # Low-level types

# %%markdown
# # Global switches

# %%markdown
# # Awkward array classes

# %%markdown
# ## JaggedArray: variable-length lists

# %%markdown
# ## Table: nested records

# %%markdown
# ## MaskedArray: nullable data

# %%markdown
# ## UnionArray: heterogeneous lists

# %%markdown
# ## ObjectArray and Methods: interactivity in Python

# %%markdown
# ## StringArray: strings

# %%markdown
# ## IndexedArray: cross-references and circular references

# %%markdown
# ## SparseArray: sparse data

# %%markdown
# ## ChunkedArray: non-contiguous data

# %%markdown
# ## AppendableArray: efficiently add rows of data

# %%markdown
# ## VirtualArray: data on demand

# %%markdown
# # Serialization: reading and writing data

# %%markdown
# ## JSON and Python data

# %%markdown
# ## Awkward files

# %%markdown
# ## HDF5

# %%markdown
# ## Pickle

# %%markdown
# ## Arrow

# %%markdown
# ## Parquet

# %%markdown
# ## ROOT

# %%markdown
# ## Persist virtual: mixed-source data

# %%markdown
# # Using Pandas with awkward arrays

# %%markdown
# # Using Numba with awkward arrays

# %%markdown
# # Flattening awkard arrays for machine learning
