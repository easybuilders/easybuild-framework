# External compatible license
"""
This work is licensed under a Creative Commons Attribution-ShareAlike 3.0 Unported License
with attribution required

Original code by http://stackoverflow.com/users/416467/kindall from answer 4 of
http://stackoverflow.com/questions/9057669/how-can-i-intercept-calls-to-pythons-magic-methods-in-new-style-classes
"""
from easybuild.tools.py2vs3 import mk_wrapper_baseclass


class WrapperMeta(type):
    """Metaclass for type wrappers."""

    def __init__(cls, name, bases, dct):

        def make_proxy(name):
            def proxy(self, *args):  # pylint:disable=unused-argument
                return getattr(self._obj, name)
            return proxy

        # create proxies for wrapped object's double-underscore attributes
        type.__init__(cls, name, bases, dct)
        if cls.__wraps__:
            ignore = set("__%s__" % n for n in cls.__ignore__.split())
            for name in dir(cls.__wraps__):
                if name.startswith("__"):
                    if name not in ignore and name not in dct:
                        setattr(cls, name, property(make_proxy(name)))


class Wrapper(mk_wrapper_baseclass(WrapperMeta)):
    """
    Wrapper class that provides proxy access to an instance of some internal instance.
    """
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
