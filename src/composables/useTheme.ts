import { ref, watch, computed } from 'vue'

type Theme = 'light' | 'dark' | 'contrast'
type FontSize = 'sm' | 'base' | 'lg' | 'xl'
type Glove = 'off' | 'on'

const KEY_THEME = 'app:theme'
const KEY_FONT = 'app:fontsize'
const KEY_GLOVE = 'app:glove'

const FONT_LEVELS: FontSize[] = ['sm', 'base', 'lg', 'xl']
const FONT_LABELS: Record<FontSize, string> = { sm: '小', base: '标准', lg: '大', xl: '特大' }

const theme = ref<Theme>((localStorage.getItem(KEY_THEME) as Theme) || 'light')
const fontSize = ref<FontSize>((localStorage.getItem(KEY_FONT) as FontSize) || 'base')
const glove = ref<Glove>((localStorage.getItem(KEY_GLOVE) as Glove) || 'off')

const apply = () => {
  const html = document.documentElement
  html.dataset.theme = theme.value
  html.dataset.fontsize = fontSize.value
  html.dataset.glove = glove.value
}
apply()

watch(theme, v => { localStorage.setItem(KEY_THEME, v); apply() })
watch(fontSize, v => { localStorage.setItem(KEY_FONT, v); apply() })
watch(glove, v => { localStorage.setItem(KEY_GLOVE, v); apply() })

const fontIndex = computed(() => FONT_LEVELS.indexOf(fontSize.value))
const fontSizeLabel = computed(() => FONT_LABELS[fontSize.value])

export function useTheme() {
  const toggleDark = () => { theme.value = theme.value === 'dark' ? 'light' : 'dark' }
  const toggleContrast = () => { theme.value = theme.value === 'contrast' ? 'light' : 'contrast' }
  const setTheme = (t: Theme) => { theme.value = t }
  const setFontSize = (s: FontSize) => { fontSize.value = s }
  const toggleGlove = () => { glove.value = glove.value === 'on' ? 'off' : 'on' }

  const increaseFontSize = () => {
    const i = fontIndex.value
    if (i < FONT_LEVELS.length - 1) fontSize.value = FONT_LEVELS[i + 1]
  }
  const decreaseFontSize = () => {
    const i = fontIndex.value
    if (i > 0) fontSize.value = FONT_LEVELS[i - 1]
  }
  const resetFontSize = () => { fontSize.value = 'base' }

  return {
    theme, fontSize, glove,
    fontSizeLabel,
    toggleDark, toggleContrast, setTheme, setFontSize, toggleGlove,
    increaseFontSize, decreaseFontSize, resetFontSize
  }
}
