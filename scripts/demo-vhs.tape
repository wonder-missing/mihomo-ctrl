Output docs/demo.gif

Require echo

Set Shell "bash"
Set FontFamily "Menlo, Hiragino Sans GB"
Set FontSize 20
Set LineHeight 1.0
Set LetterSpacing 0
Set Width 960
Set Height 720
Set Padding 0
Set WindowBar Colorful
Set WindowBarSize 40
Set Theme "Catppuccin Mocha"
Set TypingSpeed 50ms
Set CursorBlink false
Set Framerate 30
Set WaitTimeout 20s

Env TERM "xterm-256color"
Env COLORTERM "truecolor"
Env MIHOMO_API_URL "http://127.0.0.1:18765"

Hide
Type "source .demo-env"
Enter
Type "clear"
Enter
Sleep 200ms
Show
Sleep 500ms

Type "mihomo-ctrl lsg"
Enter
Wait+Screen /Mihomo Proxy Groups/
Sleep 2.8s

Ctrl+L
Sleep 200ms

Type "mihomo-ctrl lsg 美国"
Enter
Wait+Screen /Proxy Group: 美国/
Sleep 3.2s

Ctrl+L
Sleep 200ms

Type "mihomo-ctrl switch 默认 美国"
Enter
Wait+Screen /Switched proxy group/
Sleep 2s

Type "mihomo-ctrl lsg"
Enter
Wait+Screen /默认 -> 美国/
Sleep 2.8s

Ctrl+L
Sleep 200ms

Type "mihomo-ctrl tui"
Enter
Wait+Screen /代理组/
Sleep 3.5s
