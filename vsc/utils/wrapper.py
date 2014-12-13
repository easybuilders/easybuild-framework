"""
This work is licensed under a Creative Commons Attribution-ShareAlike 3.0 Unported License 
with attribution required

Original code by http://stackoverflow.com/users/416467/kindall from answer 4 of
http://stackoverflow.com/questions/9057669/how-can-i-intercept-calls-to-pythons-magic-methods-in-new-style-classes
"""
class Wrapper(object):
    """Wrapper class that provides proxy access to an instance of some
       internal instance."""

    __wraps__ = None
    __ignore__ = "class mro new init setattr getattr getattribute"

    def __init__(self, obj):
        if self.__wraps__ is None:
            raise TypeError("base class Wrapper may not be instantiated")
        elif isinstance(obj, self.__wraps__):
            self._obj = obj
        else:
            raise ValueError("wrapped object must be of %s" % self.__wraps__)

    # provide proxy access to regular attributes of wrapped object
    def __getattr__(self, name):
        return getattr(self._obj, name)

    # create proxies for wrapped object's double-underscore attributes
    class __metaclass__(type):
        def __init__(cls, name, bases, dct):

            def make_proxy(name):
                def proxy(self, *args):
                    return getattr(self._obj, name)
                return proxy

            type.__init__(cls, name, bases, dct)
            if cls.__wraps__:
                ignore = set("__%s__" % n for n in cls.__ignore__.split())
                for name in dir(cls.__wraps__):
                    if name.startswith("__"):
                        if name not in ignore and name not in dct:
                            setattr(cls, name, property(make_proxy(name)))


class HybridListDict(Wrapper):
    """
    Hybrid list/dict object: is a list of 2-element tuples, but also acts like a dict.

    Supported dict-like methods include: update(adict), items(), keys(), values()
    """
    __wraps__ = list

    def __getitem__(self, index_key):
        """Get value by specified index/key."""
        if isinstance(index_key, int):
            res = self._obj[index_key]
        else:
            res = dict(self._obj)[index_key]
        return res

    def __setitem__(self, index_key, value):
        """Add value at specified index/key."""
        if isinstance(index_key, int):
            self._obj[index_key] = value
        else:
            self._obj = [(k, v) for (k, v) in self._obj if k != index_key]
            self._obj.append((index_key, value))

    def update(self, extra):
        """Update with keys/values in supplied dictionary."""
        self._obj = [(k, v) for (k, v) in self._obj if k not in extra.keys()]
        self._obj.extend(extra.items())

    def items(self):
        """Get list of key/value tuples."""
        return self._obj

    def keys(self):
        """Get list of keys."""
        return [x[0] for x in self.items()]

    def values(self):
        """Get list of values."""
        return [x[1] for x in self.items()]
