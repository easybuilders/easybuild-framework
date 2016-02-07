import pkg_resources
pkg_resources.declare_namespace('.'.join(__name__.split('.')[:-1]))
