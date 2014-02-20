#******************************************************************************\
# * Copyright (c) 2003-2004, Martin Blais
# * All rights reserved.
# *
# * Redistribution and use in source and binary forms, with or without
# * modification, are permitted provided that the following conditions are
# * met:
# *
# * * Redistributions of source code must retain the above copyright
# *   notice, this list of conditions and the following disclaimer.
# *
# * * Redistributions in binary form must reproduce the above copyright
# *   notice, this list of conditions and the following disclaimer in the
# *   documentation and/or other materials provided with the distribution.
# *
# * * Neither the name of the Martin Blais, Furius, nor the names of its
# *   contributors may be used to endorse or promote products derived from
# *   this software without specific prior written permission.
# *
# * THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS
# * "AS IS" AND ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT
# * LIMITED TO, THE IMPLIED WARRANTIES OF MERCHANTABILITY AND FITNESS FOR
# * A PARTICULAR PURPOSE ARE DISCLAIMED. IN NO EVENT SHALL THE COPYRIGHT
# * OWNER OR CONTRIBUTORS BE LIABLE FOR ANY DIRECT, INDIRECT, INCIDENTAL,
# * SPECIAL, EXEMPLARY, OR CONSEQUENTIAL DAMAGES (INCLUDING, BUT NOT
# * LIMITED TO, PROCUREMENT OF SUBSTITUTE GOODS OR SERVICES; LOSS OF USE,
# * DATA, OR PROFITS; OR BUSINESS INTERRUPTION) HOWEVER CAUSED AND ON ANY
# * THEORY OF LIABILITY, WHETHER IN CONTRACT, STRICT LIABILITY, OR TORT
# * (INCLUDING NEGLIGENCE OR OTHERWISE) ARISING IN ANY WAY OUT OF THE USE
# * OF THIS SOFTWARE, EVEN IF ADVISED OF THE POSSIBILITY OF SUCH DAMAGE.
#******************************************************************************\
#
# stdweird: This is a copy of etc/optcomplete.bash (changeset 17:e0a9131a94cc)
# stdweird:     source: https://hg.furius.ca/public/optcomplete
#
# optcomplete harness for bash shell. You then need to tell
# bash to invoke this shell function with a command like
# this:
#
#   complete -F _optcomplete <your command>
#

_optcomplete()
{
    # needed to let it return _filedir based commands
    local cur prev quoted
    _get_comp_words_by_ref cur prev
    _quote_readline_by_ref "$cur" quoted
    _expand || return 0

    # call the command with the completion information, then eval it's results so it can call _filedir or similar
    # this does have the potential to be a security problem, especially if running as root, but we should trust
    # the completions as we're planning to run this script anyway
    eval $( \
            COMP_LINE=$COMP_LINE  COMP_POINT=$COMP_POINT \
            COMP_WORDS="${COMP_WORDS[*]}"  COMP_CWORD=$COMP_CWORD \
            OPTPARSE_AUTO_COMPLETE=1 $1
        )
}
