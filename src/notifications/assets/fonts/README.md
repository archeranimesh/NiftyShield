# Roboto Fonts

Downloaded from Google Fonts:
- Font: https://raw.githubusercontent.com/google/fonts/main/ofl/roboto/Roboto%5Bwdth%2Cwght%5D.ttf
- License: https://raw.githubusercontent.com/google/fonts/main/ofl/roboto/OFL.txt

## Extraction

The static fonts were extracted from the variable font using `fontTools.varLib.instancer` with the following python script:

```python
import fontTools.varLib.instancer as instancer
from fontTools.ttLib import TTFont

# Regular (wght 400)
font = TTFont('Roboto-VF.ttf')
font_reg = instancer.instantiateVariableFont(font, {"wdth": 100, "wght": 400}, updateFontNames=True)
font_reg.save('Roboto-Regular.ttf')

# Bold (wght 700)
font = TTFont('Roboto-VF.ttf')
font_bold = instancer.instantiateVariableFont(font, {"wdth": 100, "wght": 700}, updateFontNames=True)
font_bold.save('Roboto-Bold.ttf')
```

## Verifications
Two facts were confirmed for these generated files:
1. The Indian Rupee symbol (₹, U+20B9) is present in both TTFs.
2. The digits `0`-`9` share a single advance width within each weight (tabular figures): 1151 for Regular, 1175 for Bold.
