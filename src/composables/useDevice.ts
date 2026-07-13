import { ref, onMounted, onBeforeUnmount, computed } from 'vue'

export type DeviceKind = 'pc' | 'tablet' | 'mobile'

const SPLIT_TABLET = 640
const SPLIT_PC = 1024

/** 监听窗口尺寸返回 'pc' | 'tablet' | 'mobile'。tablet 默认走 mobile 布局。 */
export function useDevice() {
  const width = ref(typeof window !== 'undefined' ? window.innerWidth : 1920)

  const onResize = () => { width.value = window.innerWidth }

  onMounted(() => window.addEventListener('resize', onResize))
  onBeforeUnmount(() => window.removeEventListener('resize', onResize))

  const device = computed<DeviceKind>(() => {
    if (width.value < SPLIT_TABLET) return 'mobile'
    if (width.value < SPLIT_PC) return 'tablet'
    return 'pc'
  })

  const isMobile = computed(() => device.value !== 'pc')
  const isPC = computed(() => device.value === 'pc')

  return { device, width, isMobile, isPC }
}
