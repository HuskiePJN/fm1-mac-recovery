# loader/

`./setup.sh` downloads `wl82loader.bin` here: JieLi's USB flash loader for the WL82 / AC791N, from
[jl-uboot-tool](https://github.com/kagaimiq/jl-uboot-tool) (MIT), commit `adb3f18`. It is not
included in this repository. `fm1_recover.py` checks its SHA-256
(`d41da6126760c9d66660bcc0cac8d27d221806c5e369a8036921efe68dca5376`) and refuses any other file.
