from textual.theme import Theme

# https://lospec.com/palette-list/nostalgos-12
OGHAM_THEME = Theme(
    name='ogham',
    primary='#5A8BDE',
    secondary='#55927F',
    accent='#B89CE9',
    foreground='#DAD4C9',
    background='#272A32',
    surface='#21525A',
    panel='#2152a5',
    boost='#DEADA5',
    warning='#EEB24A',
    error='#DC6250',
    success='#55927F',
    dark=True,
    variables={
        'footer-key-foreground': '#FFD183',
        'input-selection-background': '#5A8BDE 40%',
    },
)
