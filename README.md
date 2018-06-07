# mpdmenu - mpd client powered by dmenu and python-mpd2 
`mpdmenu` is a Python3 script that uses `dmenu` or any other dmenu-like menu for X (e.g. `rofi`) to control `mpd`.

# Usage

```
mpdmenu [options] [dmenu_cmd]

        dmenu_cmd
            command line to execute on new state (defaults to "dmenu")

    Options
        -a ADDRESS, --address=ADDRESS
            Address used to connect to mpd (defaults to 'localhost')

        -p PORT, --port=PORT
            Port used to connect to mpd. Must be a number (defaults to 6600)

        -t TIMEOUT, --timeout
            Timeout of connection. Must be a number (defaults to 60)
```
