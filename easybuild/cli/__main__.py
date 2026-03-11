from easybuild.cli import eb

# Ensure Click to recognizes the program name as `eb` when invoked as `python -m easybuild.cli` or similar
eb(prog_name='eb')
