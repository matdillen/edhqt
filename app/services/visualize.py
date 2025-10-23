import re

def mana_symbol_html(code: str):
    code_id = code.lower()
    if code_id.isdigit() or code_id == "x":
        return f'''<span class="mana-symbol">
            <img class="mana-bg" src="app/static/mana/mana_circle.png" alt="{code_id}" width="12" height="12"/><span class="mana-text"">{code_id}</span>
            </span>
            '''
    else:
        return f'<img class="mana-symbol" src="app/static/mana/mana_{code_id}.png" alt="{code_id}" width="12" height="12"/>'

def manafy_html(text: str):
    """Replace all {X} mana symbols in text with corresponding <img> tags."""
    pattern = re.compile(r"\{(.*?)\}")
    def replacer(match):
        code = match.group(1)
        return mana_symbol_html(code)
    return pattern.sub(replacer, text)