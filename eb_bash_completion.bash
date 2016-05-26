_eb()
{
    local cur prev quoted
    _get_comp_words_by_ref cur prev
    _quote_readline_by_ref "$cur" quoted

	case $cur in 
		--*) _optcomplete "$@"; return 0 ;;
		*)  COMPREPLY=( $(compgen -f -X '!*.eb' -- $cur ) \
                        $(compgen -W "$($1 --search-file ${cur:-eb} --terse)" -- $cur) ) ;;
	esac
}
complete -F _eb eb
