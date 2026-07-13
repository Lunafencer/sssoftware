import { ref } from 'vue'

/** AI 流式打字机输出。usage:
 *   const { display, run, done } = useStreamText()
 *   run('一段长文本…')
 */
export function useStreamText(speed = 28) {
  const display = ref('')
  const done = ref(true)
  let timer: number | null = null

  const stop = () => { if (timer) { clearInterval(timer); timer = null } }

  const run = (full: string) => {
    stop()
    display.value = ''
    done.value = false
    let i = 0
    timer = window.setInterval(() => {
      i++
      display.value = full.slice(0, i)
      if (i >= full.length) {
        stop()
        done.value = true
      }
    }, speed)
  }

  return { display, done, run, stop }
}
