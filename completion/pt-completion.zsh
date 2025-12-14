#compdef pt

# Zsh completion for pt
#
# Installation:
#   Add to ~/.zshrc:
#     eval "$(_PT_COMPLETE=zsh_source pt)"
#
#   Or install to a directory in $fpath:
#     _PT_COMPLETE=zsh_source pt > ~/.zsh/completions/_pt
#     # Ensure ~/.zsh/completions is in your $fpath
#
#   Or install system-wide:
#     _PT_COMPLETE=zsh_source pt > /usr/local/share/zsh/site-functions/_pt

_pt_completion() {
    local -a completions
    local -a completions_with_descriptions
    local -a response
    (( ! $+commands[pt] )) && return 1

    response=("${(@f)$(env COMP_WORDS="${words[*]}" COMP_CWORD=$((CURRENT-1)) _PT_COMPLETE=zsh_complete pt)}")

    for type key descr in ${response}; do
        if [[ "$type" == "plain" ]]; then
            if [[ "$descr" == "_" ]]; then
                completions+=("$key")
            else
                completions_with_descriptions+=("$key":"$descr")
            fi
        elif [[ "$type" == "dir" ]]; then
            _path_files -/
        elif [[ "$type" == "file" ]]; then
            _path_files -f
        fi
    done

    if [ -n "$completions_with_descriptions" ]; then
        _describe -V unsorted completions_with_descriptions -U
    fi

    if [ -n "$completions" ]; then
        compadd -U -V unsorted -a completions
    fi
}

compdef _pt_completion pt
