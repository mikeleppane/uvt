# Bash completion for pt
#
# Installation:
#   Add to ~/.bashrc:
#     eval "$(_PT_COMPLETE=bash_source pt)"
#
#   Or install system-wide:
#     _PT_COMPLETE=bash_source pt > /etc/bash_completion.d/pt
#
#   Or install for current user:
#     _PT_COMPLETE=bash_source pt > ~/.local/share/bash-completion/completions/pt

_pt_completion() {
    local IFS=$'\n'
    local response

    response=$(env COMP_WORDS="${COMP_WORDS[*]}" COMP_CWORD=$COMP_CWORD _PT_COMPLETE=bash_complete $1)

    for completion in $response; do
        IFS=',' read type value <<< "$completion"

        if [[ $type == 'dir' ]]; then
            COMPREPLY=()
            compopt -o dirnames
        elif [[ $type == 'file' ]]; then
            COMPREPLY=()
            compopt -o default
        elif [[ $type == 'plain' ]]; then
            COMPREPLY+=($value)
        fi
    done

    return 0
}

complete -o nosort -F _pt_completion pt
