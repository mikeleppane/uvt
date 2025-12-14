# Fish completion for pt
#
# Installation:
#   _PT_COMPLETE=fish_source pt > ~/.config/fish/completions/pt.fish

function __fish_pt_complete
    set -lx COMP_WORDS (commandline -opc) (commandline -ct)
    set -lx COMP_CWORD (math (count $COMP_WORDS) - 1)

    set -l response (env _PT_COMPLETE=fish_complete pt)

    for completion in $response
        set -l parts (string split \t $completion)
        echo $parts[1]\t$parts[2]
    end
end

complete -c pt -f -a "(__fish_pt_complete)"
