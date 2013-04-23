from pkgutil import extend_path

# we're not the only ones in this namespace
__path__ = extend_path(__path__, __name__)  #@ReservedAssignment
