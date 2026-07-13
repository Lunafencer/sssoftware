import { createApp } from 'vue'
import { createPinia } from 'pinia'
import App from './App.vue'
import router from './router'

import ElementPlus from 'element-plus'
import zhCn from 'element-plus/dist/locale/zh-cn.mjs'
import 'element-plus/dist/index.css'

import Vant from 'vant'
import 'vant/lib/index.css'

import '@/assets/styles/tokens.css'
import '@/assets/styles/globals.css'
import '@/assets/styles/industrial.css'
import '@/assets/styles/tailwind.css'

const app = createApp(App)
app.use(createPinia())
app.use(router)
app.use(ElementPlus, { locale: zhCn })
app.use(Vant)

app.mount('#app')

// 刷新后用已存的 token 回填当前用户信息（用户资料不再写 localStorage）
import { useUserStore } from '@/stores/user'
useUserStore().hydrate()

// 启动屏移除
const splash = document.getElementById('splash')
if (splash) {
  setTimeout(() => {
    splash.style.transition = 'opacity .35s ease'
    splash.style.opacity = '0'
    setTimeout(() => splash.remove(), 400)
  }, 300)
}
