# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation; either version 2, or (at your option)
# any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program; if not, write to the Free Software Foundation,
# Inc., 59 Temple Place - Suite 330, Boston, MA 02111-1307, USA.

#
# Modifications by stdweird:
#   These are minimal set of functions to make autocompletion and optcomplete work on pre-bash 4.2
#   They are taken from https://github.com/brianzimmer/dotfiles/blob/master/bashcompletion/bash_completion
#   which is version 1.3 of the bash_completion project from http://bash-completion.alioth.debian.org/
#   So these too are GPLv2 or later
#   The functions are wrapped in conditionals to check if the functions already exist or not (eg set via OS environment)
# 

type _quote_readline_by_ref >& /dev/null
if [ $? -ne 0 ]
then # begin _quote_readline_by_ref conditional

# This function quotes the argument in a way so that readline dequoting
# results in the original argument.  This is necessary for at least
# `compgen' which requires its arguments quoted/escaped:
#
#     $ ls "a'b/"
#     c
#     $ compgen -f "a'b/"       # Wrong, doesn't return output
#     $ compgen -f "a\'b/"      # Good (bash-4)
#     a\'b/c
#     $ compgen -f "a\\\\\'b/"  # Good (bash-3)
#     a\'b/c
#
# On bash-3, special characters need to be escaped extra.  This is
# unless the first character is a single quote (').  If the single
# quote appears further down the string, bash default completion also
# fails, e.g.:
#
#     $ ls 'a&b/'
#     f
#     $ foo 'a&b/<TAB>  # Becomes: foo 'a&b/f'
#     $ foo a'&b/<TAB>  # Nothing happens
#
# See also:
# - http://lists.gnu.org/archive/html/bug-bash/2009-03/msg00155.html
# - http://www.mail-archive.com/bash-completion-devel@lists.alioth.\
#   debian.org/msg01944.html
# @param $1  Argument to quote
# @param $2  Name of variable to return result to

_quote_readline_by_ref()
{
    if [[ ${1:0:1} == "'" ]]; then
        if [[ ${BASH_VERSINFO[0]} -ge 4 ]]; then
            # Leave out first character
            printf -v $2 %s "${1:1}"
        else
            # Quote word, leaving out first character
            printf -v $2 %q "${1:1}"
            # Double-quote word (bash-3)
            printf -v $2 %q ${!2}
        fi
    elif [[ ${BASH_VERSINFO[0]} -le 3 && ${1:0:1} == '"' ]]; then
        printf -v $2 %q "${1:1}"
    else
        printf -v $2 %q "$1"
    fi

    # If result becomes quoted like this: $'string', re-evaluate in order to
    # drop the additional quoting.  See also: http://www.mail-archive.com/
    # bash-completion-devel@lists.alioth.debian.org/msg01942.html
    [[ ${!2:0:1} == '$' ]] && eval $2=${!2}
} # _quote_readline_by_ref()

fi # end _quote_readline_by_ref conditional

type _expand >& /dev/null
if [ $? -ne 0 ]
then # begin _expand conditional

# This function expands tildes in pathnames
#
_expand()
{
    # FIXME: Why was this here?
    #[ "$cur" != "${cur%\\}" ] && cur="$cur\\"

    # Expand ~username type directory specifications.  We want to expand
    # ~foo/... to /home/foo/... to avoid problems when $cur starting with
    # a tilde is fed to commands and ending up quoted instead of expanded.

    if [[ "$cur" == \~*/* ]]; then
        eval cur=$cur
    elif [[ "$cur" == \~* ]]; then
        cur=${cur#\~}
        COMPREPLY=( $( compgen -P '~' -u "$cur" ) )
        [ ${#COMPREPLY[@]} -eq 1 ] && eval COMPREPLY[0]=${COMPREPLY[0]}
        return ${#COMPREPLY[@]}
    fi
}

fi # end _expand conditional

type _get_comp_words_by_ref >& /dev/null
if [ $? -ne 0 ]
then # begin _get_comp_words_by_ref conditional

# Reassemble command line words, excluding specified characters from the
# list of word completion separators (COMP_WORDBREAKS).
# @param $1 chars  Characters out of $COMP_WORDBREAKS which should
#     NOT be considered word breaks. This is useful for things like scp where
#     we want to return host:path and not only path, so we would pass the
#     colon (:) as $1 here.
# @param $2 words  Name of variable to return words to
# @param $3 cword  Name of variable to return cword to
#
__reassemble_comp_words_by_ref() {
    local exclude i j ref
    # Exclude word separator characters?
    if [[ $1 ]]; then
        # Yes, exclude word separator characters;
        # Exclude only those characters, which were really included
        exclude="${1//[^$COMP_WORDBREAKS]}"
    fi
        
    # Default to cword unchanged
    eval $3=$COMP_CWORD
    # Are characters excluded which were former included?
    if [[ $exclude ]]; then
        # Yes, list of word completion separators has shrunk;
        # Re-assemble words to complete
        for (( i=0, j=0; i < ${#COMP_WORDS[@]}; i++, j++)); do
            # Is current word not word 0 (the command itself) and is word not
            # empty and is word made up of just word separator characters to be
            # excluded?
            while [[ $i -gt 0 && ${COMP_WORDS[$i]} && 
                ${COMP_WORDS[$i]//[^$exclude]} == ${COMP_WORDS[$i]} 
            ]]; do
                [ $j -ge 2 ] && ((j--))
                # Append word separator to current word
                ref="$2[$j]"
                eval $2[$j]=\${!ref}\${COMP_WORDS[i]}
                # Indicate new cword
                [ $i = $COMP_CWORD ] && eval $3=$j
                # Indicate next word if available, else end *both* while and for loop
                (( $i < ${#COMP_WORDS[@]} - 1)) && ((i++)) || break 2
            done
            # Append word to current word
            ref="$2[$j]"
            eval $2[$j]=\${!ref}\${COMP_WORDS[i]}
            # Indicate new cword
            [[ $i == $COMP_CWORD ]] && eval $3=$j
        done
    else
        # No, list of word completions separators hasn't changed;
        eval $2=\( \"\${COMP_WORDS[@]}\" \)
    fi
} # __reassemble_comp_words_by_ref()

# Assign variables one scope above the caller
# Usage: local varname [varname ...] && 
#        _upvars [-v varname value] | [-aN varname [value ...]] ...
# Available OPTIONS:
#     -aN  Assign next N values to varname as array
#     -v   Assign single value to varname
# Return: 1 if error occurs
# See: http://fvue.nl/wiki/Bash:_Passing_variables_by_reference
_upvars() {
    if ! (( $# )); then
        echo "${FUNCNAME[0]}: usage: ${FUNCNAME[0]} [-v varname"\
            "value] | [-aN varname [value ...]] ..." 1>&2
        return 2
    fi
    while (( $# )); do
        case $1 in
            -a*)
                # Error checking
                [[ ${1#-a} ]] || { echo "bash: ${FUNCNAME[0]}: \`$1': missing"\
                    "number specifier" 1>&2; return 1; }
                printf %d "${1#-a}" &> /dev/null || { echo "bash:"\
                    "${FUNCNAME[0]}: \`$1': invalid number specifier" 1>&2
                    return 1; }
                # Assign array of -aN elements
                [[ "$2" ]] && unset -v "$2" && eval $2=\(\"\${@:3:${1#-a}}\"\) && 
                shift $((${1#-a} + 2)) || { echo "bash: ${FUNCNAME[0]}:"\
                    "\`$1${2+ }$2': missing argument(s)" 1>&2; return 1; }
                ;;
            -v)
                # Assign single value
                [[ "$2" ]] && unset -v "$2" && eval $2=\"\$3\" &&
                shift 3 || { echo "bash: ${FUNCNAME[0]}: $1: missing"\
                "argument(s)" 1>&2; return 1; }
                ;;
            *)
                echo "bash: ${FUNCNAME[0]}: $1: invalid option" 1>&2
                return 1 ;;
        esac
    done
}

# @param $1 exclude  Characters out of $COMP_WORDBREAKS which should NOT be
#     considered word breaks. This is useful for things like scp where
#     we want to return host:path and not only path, so we would pass the
#     colon (:) as $1 in this case.  Bash-3 doesn't do word splitting, so this
#     ensures we get the same word on both bash-3 and bash-4.
# @param $2 words  Name of variable to return words to
# @param $3 cword  Name of variable to return cword to
# @param $4 cur  Name of variable to return current word to complete to
# @see ___get_cword_at_cursor_by_ref()
__get_cword_at_cursor_by_ref() {
    local cword words=()
    __reassemble_comp_words_by_ref "$1" words cword

    local i cur2
    local cur="$COMP_LINE"
    local index="$COMP_POINT"
    for (( i = 0; i <= cword; ++i )); do
        while [[
            # Current word fits in $cur?
            "${#cur}" -ge ${#words[i]} &&
            # $cur doesn't match cword?
            "${cur:0:${#words[i]}}" != "${words[i]}"
        ]]; do
            # Strip first character
            cur="${cur:1}"
            # Decrease cursor position
            ((index--))
        done

        # Does found word matches cword?
        if [[ "$i" -lt "$cword" ]]; then
            # No, cword lies further;
            local old_size="${#cur}"
            cur="${cur#${words[i]}}"
            local new_size="${#cur}"
            index=$(( index - old_size + new_size ))
        fi
    done

    if [[ "${words[cword]:0:${#cur}}" != "$cur" ]]; then
        # We messed up. At least return the whole word so things keep working
        cur2=${words[cword]}
    else
        cur2=${cur:0:$index}
    fi

    local "$2" "$3" "$4" && 
        _upvars -a${#words[@]} $2 "${words[@]}" -v $3 "$cword" -v $4 "$cur2"
}


# Get the word to complete and optional previous words.
# This is nicer than ${COMP_WORDS[$COMP_CWORD]}, since it handles cases
# where the user is completing in the middle of a word.
# (For example, if the line is "ls foobar",
# and the cursor is here -------->   ^
# Also one is able to cross over possible wordbreak characters.
# Usage: _get_comp_words_by_ref [OPTIONS] [VARNAMES]
# Available VARNAMES:
#     cur         Return cur via $cur
#     prev        Return prev via $prev
#     words       Return words via $words
#     cword       Return cword via $cword
#
# Available OPTIONS:
#     -n EXCLUDE  Characters out of $COMP_WORDBREAKS which should NOT be 
#                 considered word breaks. This is useful for things like scp
#                 where we want to return host:path and not only path, so we
#                 would pass the colon (:) as -n option in this case.  Bash-3
#                 doesn't do word splitting, so this ensures we get the same
#                 word on both bash-3 and bash-4.
#     -c VARNAME  Return cur via $VARNAME
#     -p VARNAME  Return prev via $VARNAME
#     -w VARNAME  Return words via $VARNAME
#     -i VARNAME  Return cword via $VARNAME
#
# Example usage:
#
#    $ _get_comp_words_by_ref -n : cur prev
#
_get_comp_words_by_ref()
{
    local exclude flag i OPTIND=1
    local cur cword words=()
    local upargs=() upvars=() vcur vcword vprev vwords

    while getopts "c:i:n:p:w:" flag "$@"; do
        case $flag in
            c) vcur=$OPTARG ;;
            i) vcword=$OPTARG ;;
            n) exclude=$OPTARG ;;
            p) vprev=$OPTARG ;;
            w) vwords=$OPTARG ;;
        esac
    done
    while [[ $# -ge $OPTIND ]]; do 
        case ${!OPTIND} in
            cur)   vcur=cur ;;
            prev)  vprev=prev ;;
            cword) vcword=cword ;;
            words) vwords=words ;;
            *) echo "bash: $FUNCNAME(): \`${!OPTIND}': unknown argument" \
                1>&2; return 1
        esac
        let "OPTIND += 1"
    done

    __get_cword_at_cursor_by_ref "$exclude" words cword cur

    [[ $vcur   ]] && { upvars+=("$vcur"  ); upargs+=(-v $vcur   "$cur"  ); }
    [[ $vcword ]] && { upvars+=("$vcword"); upargs+=(-v $vcword "$cword"); }
    [[ $vprev  ]] && { upvars+=("$vprev" ); upargs+=(-v $vprev 
        "${words[cword - 1]}"); }
    [[ $vwords ]] && { upvars+=("$vwords"); upargs+=(-a${#words[@]} $vwords
        "${words[@]}"); }

    (( ${#upvars[@]} )) && local "${upvars[@]}" && _upvars "${upargs[@]}"
}

fi # end _get_comp_words_by_ref conditional

type _filedir >& /dev/null
if [ $? -ne 0 ]
then # begin _filedir conditional

# This function turns on "-o filenames" behavior dynamically. It is present
# for bash < 4 reasons. See http://bugs.debian.org/272660#64 for info about
# the bash < 4 compgen hack.
_compopt_o_filenames()
{
    # We test for compopt availability first because directly invoking it on
    # bash < 4 at this point may cause terminal echo to be turned off for some
    # reason, see https://bugzilla.redhat.com/653669 for more info.
    type compopt &>/dev/null && compopt -o filenames 2>/dev/null || \
        compgen -f /non-existing-dir/ >/dev/null
}

# Perform tilde (~) completion
# @return  True (0) if completion needs further processing, 
#          False (> 0) if tilde is followed by a valid username, completions
#          are put in COMPREPLY and no further processing is necessary.
_tilde() {
    local result=0
    # Does $1 start with tilde (~) and doesn't contain slash (/)?
    if [[ ${1:0:1} == "~" && $1 == ${1//\/} ]]; then
        _compopt_o_filenames
        # Try generate username completions
        COMPREPLY=( $( compgen -P '~' -u "${1#\~}" ) )
        result=${#COMPREPLY[@]}
    fi
    return $result
}

# This function performs file and directory completion. It's better than
# simply using 'compgen -f', because it honours spaces in filenames.
# @param $1  If `-d', complete only on directories.  Otherwise filter/pick only
#            completions with `.$1' and the uppercase version of it as file
#            extension.
#
_filedir()
{
    local i IFS=$'\n' xspec

    _tilde "$cur" || return 0

    local -a toks
    local quoted tmp

    _quote_readline_by_ref "$cur" quoted
    toks=( ${toks[@]-} $(
        compgen -d -- "$quoted" | {
            while read -r tmp; do
                # TODO: I have removed a "[ -n $tmp ] &&" before 'printf ..',
                #       and everything works again. If this bug suddenly
                #       appears again (i.e. "cd /b<TAB>" becomes "cd /"),
                #       remember to check for other similar conditionals (here
                #       and _filedir_xspec()). --David
                printf '%s\n' $tmp
            done
        }
    ))

    if [[ "$1" != -d ]]; then
        # Munge xspec to contain uppercase version too
        [[ ${BASH_VERSINFO[0]} -ge 4 ]] && \
            xspec=${1:+"!*.@($1|${1^^})"} || \
            xspec=${1:+"!*.@($1|$(printf %s $1 | tr '[:lower:]' '[:upper:]'))"}
        toks=( ${toks[@]-} $( compgen -f -X "$xspec" -- $quoted) )
    fi
    [ ${#toks[@]} -ne 0 ] && _compopt_o_filenames

    COMPREPLY=( "${COMPREPLY[@]}" "${toks[@]}" )
} # _filedir()

fi # end _filedir conditional

type _known_hosts >& /dev/null
if [ $? -ne 0 ]
then # begin _known_hosts conditional

# NOTE: Using this function as a helper function is deprecated.  Use
#       `_known_hosts_real' instead.
_known_hosts()
{
    local options
    COMPREPLY=()

    # NOTE: Using `_known_hosts' as a helper function and passing options
    #       to `_known_hosts' is deprecated: Use `_known_hosts_real' instead.
    [[ "$1" == -a || "$2" == -a ]] && options=-a
    [[ "$1" == -c || "$2" == -c ]] && options="$options -c"
    _known_hosts_real $options "$(_get_cword :)"
} # _known_hosts()

# Expand variable starting with tilde (~)
# We want to expand ~foo/... to /home/foo/... to avoid problems when
# word-to-complete starting with a tilde is fed to commands and ending up
# quoted instead of expanded.
# Only the first portion of the variable from the tilde up to the first slash
# (~../) is expanded.  The remainder of the variable, containing for example
# a dollar sign variable ($) or asterisk (*) is not expanded.
# Example usage:
#
#    $ v="~"; __expand_tilde_by_ref v; echo "$v"
#
# Example output:
#
#       v                  output
#    --------         ----------------
#    ~                /home/user
#    ~foo/bar         /home/foo/bar
#    ~foo/$HOME       /home/foo/$HOME
#    ~foo/a  b        /home/foo/a  b
#    ~foo/*           /home/foo/*
#  
# @param $1  Name of variable (not the value of the variable) to expand
__expand_tilde_by_ref() {
    # Does $1 start with tilde (~)?
    if [ "${!1:0:1}" = "~" ]; then
        # Does $1 contain slash (/)?
        if [ "${!1}" != "${!1//\/}" ]; then
            # Yes, $1 contains slash;
            # 1: Remove * including and after first slash (/), i.e. "~a/b"
            #    becomes "~a".  Double quotes allow eval.
            # 2: Remove * before the first slash (/), i.e. "~a/b"
            #    becomes "b".  Single quotes prevent eval.
            #       +-----1----+ +---2----+
            eval $1="${!1/%\/*}"/'${!1#*/}'
        else 
            # No, $1 doesn't contain slash
            eval $1="${!1}"
        fi
    fi
} # __expand_tilde_by_ref()

# If the word-to-complete contains a colon (:), left-trim COMPREPLY items with
# word-to-complete.
# On bash-3, and bash-4 with a colon in COMP_WORDBREAKS, words containing
# colons are always completed as entire words if the word to complete contains
# a colon.  This function fixes this, by removing the colon-containing-prefix
# from COMPREPLY items.
# The preferred solution is to remove the colon (:) from COMP_WORDBREAKS in
# your .bashrc:
#
#    # Remove colon (:) from list of word completion separators
#    COMP_WORDBREAKS=${COMP_WORDBREAKS//:}
#
# See also: Bash FAQ - E13) Why does filename completion misbehave if a colon
# appears in the filename? - http://tiswww.case.edu/php/chet/bash/FAQ
# @param $1 current word to complete (cur)
# @modifies global array $COMPREPLY
#
__ltrim_colon_completions() {
    # If word-to-complete contains a colon,
    # and bash-version < 4,
    # or bash-version >= 4 and COMP_WORDBREAKS contains a colon
    if [[
        "$1" == *:* && (
            ${BASH_VERSINFO[0]} -lt 4 || 
            (${BASH_VERSINFO[0]} -ge 4 && "$COMP_WORDBREAKS" == *:*) 
        )
    ]]; then
        # Remove colon-word prefix from COMPREPLY items
        local colon_word=${1%${1##*:}}
        local i=${#COMPREPLY[*]}
        while [ $((--i)) -ge 0 ]; do
            COMPREPLY[$i]=${COMPREPLY[$i]#"$colon_word"}
        done
    fi
} # __ltrim_colon_completions()

# Helper function for completing _known_hosts.
# This function performs host completion based on ssh's config and known_hosts
# files, as well as hostnames reported by avahi-browse if
# COMP_KNOWN_HOSTS_WITH_AVAHI is set to a non-empty value.  Also hosts from
# HOSTFILE (compgen -A hostname) are added, unless
# COMP_KNOWN_HOSTS_WITH_HOSTFILE is set to an empty value.
# Usage: _known_hosts_real [OPTIONS] CWORD
# Options:  -a             Use aliases
#           -c             Use `:' suffix
#           -F configfile  Use `configfile' for configuration settings
#           -p PREFIX      Use PREFIX
# Return: Completions, starting with CWORD, are added to COMPREPLY[]
_known_hosts_real()
{
    local configfile flag prefix
    local cur curd awkcur user suffix aliases i host
    local -a kh khd config

    local OPTIND=1
    while getopts "acF:p:" flag "$@"; do
        case $flag in
            a) aliases='yes' ;;
            c) suffix=':' ;;
            F) configfile=$OPTARG ;;
            p) prefix=$OPTARG ;;
        esac
    done
    [ $# -lt $OPTIND ] && echo "error: $FUNCNAME: missing mandatory argument CWORD"
    cur=${!OPTIND}; let "OPTIND += 1"
    [ $# -ge $OPTIND ] && echo "error: $FUNCNAME("$@"): unprocessed arguments:"\
    $(while [ $# -ge $OPTIND ]; do printf '%s\n' ${!OPTIND}; shift; done)

    [[ $cur == *@* ]] && user=${cur%@*}@ && cur=${cur#*@}
    kh=()

    # ssh config files
    if [ -n "$configfile" ]; then
        [ -r "$configfile" ] &&
        config=( "${config[@]}" "$configfile" )
    else
        for i in /etc/ssh/ssh_config "${HOME}/.ssh/config" \
            "${HOME}/.ssh2/config"; do
            [ -r $i ] && config=( "${config[@]}" "$i" )
        done
    fi

    # Known hosts files from configs
    if [ ${#config[@]} -gt 0 ]; then
        local OIFS=$IFS IFS=$'\n'
        local -a tmpkh
        # expand paths (if present) to global and user known hosts files
        # TODO(?): try to make known hosts files with more than one consecutive
        #          spaces in their name work (watch out for ~ expansion
        #          breakage! Alioth#311595)
        tmpkh=( $( awk 'sub("^[ \t]*([Gg][Ll][Oo][Bb][Aa][Ll]|[Uu][Ss][Ee][Rr])[Kk][Nn][Oo][Ww][Nn][Hh][Oo][Ss][Tt][Ss][Ff][Ii][Ll][Ee][ \t]+", "") { print $0 }' "${config[@]}" | sort -u ) )
        for i in "${tmpkh[@]}"; do
            # Remove possible quotes
            i=${i//\"}
            # Eval/expand possible `~' or `~user'
            __expand_tilde_by_ref i
            [ -r "$i" ] && kh=( "${kh[@]}" "$i" )
        done
        IFS=$OIFS
    fi

    if [ -z "$configfile" ]; then
        # Global and user known_hosts files
        for i in /etc/ssh/ssh_known_hosts /etc/ssh/ssh_known_hosts2 \
            /etc/known_hosts /etc/known_hosts2 ~/.ssh/known_hosts \
            ~/.ssh/known_hosts2; do
            [ -r $i ] && kh=( "${kh[@]}" $i )
        done
        for i in /etc/ssh2/knownhosts ~/.ssh2/hostkeys; do
            [ -d $i ] && khd=( "${khd[@]}" $i/*pub )
        done
    fi

    # If we have known_hosts files to use
    if [[ ${#kh[@]} -gt 0 || ${#khd[@]} -gt 0 ]]; then
        # Escape slashes and dots in paths for awk
        awkcur=${cur//\//\\\/}
        awkcur=${awkcur//\./\\\.}
        curd=$awkcur

        if [[ "$awkcur" == [0-9]*[.:]* ]]; then
            # Digits followed by a dot or a colon - just search for that
            awkcur="^$awkcur[.:]*"
        elif [[ "$awkcur" == [0-9]* ]]; then
            # Digits followed by no dot or colon - search for digits followed
            # by a dot or a colon
            awkcur="^$awkcur.*[.:]"
        elif [ -z "$awkcur" ]; then
            # A blank - search for a dot, a colon, or an alpha character
            awkcur="[a-z.:]"
        else
            awkcur="^$awkcur"
        fi

        if [ ${#kh[@]} -gt 0 ]; then
            # FS needs to look for a comma separated list
            COMPREPLY=( "${COMPREPLY[@]}" $( awk 'BEGIN {FS=","}
            /^\s*[^|\#]/ {for (i=1; i<=2; ++i) { \
            sub(" .*$", "", $i); \
            sub("^\\[", "", $i); sub("\\](:[0-9]+)?$", "", $i); \
            if ($i ~ /'"$awkcur"'/) {print $i} \
            }}' "${kh[@]}" 2>/dev/null ) )
        fi
        if [ ${#khd[@]} -gt 0 ]; then
            # Needs to look for files called
            # .../.ssh2/key_22_<hostname>.pub
            # dont fork any processes, because in a cluster environment,
            # there can be hundreds of hostkeys
            for i in "${khd[@]}" ; do
                if [[ "$i" == *key_22_$curd*.pub && -r "$i" ]]; then
                    host=${i/#*key_22_/}
                    host=${host/%.pub/}
                    COMPREPLY=( "${COMPREPLY[@]}" $host )
                fi
            done
        fi

        # apply suffix and prefix
        for (( i=0; i < ${#COMPREPLY[@]}; i++ )); do
            COMPREPLY[i]=$prefix$user${COMPREPLY[i]}$suffix
        done
    fi

    # append any available aliases from config files
    if [[ ${#config[@]} -gt 0 && -n "$aliases" ]]; then
        local hosts=$( sed -ne 's/^[ \t]*[Hh][Oo][Ss][Tt]\([Nn][Aa][Mm][Ee]\)\{0,1\}['"$'\t '"']\{1,\}\([^#*?]*\)\(#.*\)\{0,1\}$/\2/p' "${config[@]}" )
        COMPREPLY=( "${COMPREPLY[@]}" $( compgen  -P "$prefix$user" \
            -S "$suffix" -W "$hosts" -- "$cur" ) )
    fi

    # Add hosts reported by avahi-browse, if desired and it's available.
    if [[ ${COMP_KNOWN_HOSTS_WITH_AVAHI:-} ]] && \
        type avahi-browse &>/dev/null; then
        # The original call to avahi-browse also had "-k", to avoid lookups
        # into avahi's services DB. We don't need the name of the service, and
        # if it contains ";", it may mistify the result. But on Gentoo (at
        # least), -k wasn't available (even if mentioned in the manpage) some
        # time ago, so...
        COMPREPLY=( "${COMPREPLY[@]}" $( \
            compgen -P "$prefix$user" -S "$suffix" -W \
            "$( avahi-browse -cpr _workstation._tcp 2>/dev/null | \
                 awk -F';' '/^=/ { print $7 }' | sort -u )" -- "$cur" ) )
    fi

    # Add results of normal hostname completion, unless
    # `COMP_KNOWN_HOSTS_WITH_HOSTFILE' is set to an empty value.
    if [ -n "${COMP_KNOWN_HOSTS_WITH_HOSTFILE-1}" ]; then
        COMPREPLY=( "${COMPREPLY[@]}"
            $( compgen -A hostname -P "$prefix$user" -S "$suffix" -- "$cur" ) )
    fi

    __ltrim_colon_completions "$prefix$user$cur"

    return 0
} # _known_hosts_real()

fi # end _known_hosts conditional
