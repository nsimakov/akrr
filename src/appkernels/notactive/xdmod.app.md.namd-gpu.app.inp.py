nickname = """xdmod.app.md.namd-gpu.@nnodes@"""
resourceSetName = """defaultGrid"""
action = """add"""
schedule = [
    """? ? */14 * *""",
]

name = """xdmod.app.md.namd-gpu"""
uri = """file:///home/charngda/Inca-Reporter//xdmod.app.md.namd-gpu"""
context = '''@batchpre@ -nodes=@nnodes@:@ppn@ -type=@batchFeature@ -walllimit=@walllimit@ -exec="@@"'''
arg_version = """no"""
arg_verbose = 1
arg_help = """no"""
arg_bin_path = """@bin_path@"""
arg_log = 5
walllimit=13
################################################################################
#nickname = """xdmod.app.md.namd.@namdSizes@"""
#resourceSetName = """defaultGrid"""
#action = """add"""
#schedule = [
    #"""? ? */14 * *""",
#]
#series_name = """xdmod.app.md.namd"""
#series_uri = """file:///home/charngda/Inca-Reporter//xdmod.app.md.namd"""
#series_context = '''@batchpre@ -nodes=:@ppn@:@namdSizes@ -type=@batchFeature@ -walllimit=13 -exec="@@"'''
#series_version = """no"""
#series_verbose = 1
#series_help = """no"""
#series_bin_path = """@bin_path@"""
#series_log = 5