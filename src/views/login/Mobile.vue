<script setup lang="ts">
import { ref, computed } from 'vue'
import { useRouter } from 'vue-router'
import { useUserStore } from '@/stores/user'
import { Lock, User, Cog, ChevronLeft } from 'lucide-vue-next'
import { showToast, showFailToast } from 'vant'
import { ROLE_LABEL } from '@/utils/permission'

const router = useRouter()
const user = useUserStore()

type Mode = 'login' | 'register'
const mode = ref<Mode>('login')

const username = ref('')
const password = ref('')
const confirm = ref('')
const loading = ref(false)

const switchTo = (m: Mode) => {
  mode.value = m
  password.value = ''
  confirm.value = ''
}

const onLogin = async () => {
  if (!username.value || !password.value) { showToast('请填写账号和密码'); return }
  loading.value = true
  try {
    const res = await user.login(username.value, password.value)
    showToast({ type: 'success', message: '登录成功 · ' + ROLE_LABEL[res.user.role] })
    router.push('/')
  } catch (e: any) {
    showFailToast(e?.message || '登录失败')
  } finally { loading.value = false }
}

const onRegister = async () => {
  if (!username.value || !password.value) { showToast('请填写账号和密码'); return }
  if (password.value.length < 6) { showFailToast('密码至少 6 位'); return }
  if (password.value !== confirm.value) { showFailToast('两次密码不一致'); return }
  loading.value = true
  try {
    await user.register(username.value, password.value)
    showToast({ type: 'success', message: '注册成功，请登录' })
    confirm.value = ''
    password.value = ''
    mode.value = 'login'
  } catch (e: any) {
    showFailToast(e?.message || '注册失败')
  } finally { loading.value = false }
}

const title = computed(() => mode.value === 'login' ? '欢迎使用' : '注册新账号')
</script>

<template>
  <div class="min-h-screen bg-card flex flex-col safe-top safe-bottom">
    <!-- 顶部品牌 -->
    <div class="bg-industrial-hero px-6 pt-12 pb-10 text-on-dark relative">
      <button v-if="mode === 'register'" type="button" @click="switchTo('login')"
              class="absolute left-3 top-10 w-9 h-9 rounded-full bg-white/10 flex items-center justify-center">
        <ChevronLeft class="w-5 h-5" />
      </button>
      <div class="flex items-center gap-3" :class="mode === 'register' ? 'pl-8' : ''">
        <div class="w-11 h-11 rounded bg-gradient-to-br from-accent to-accent-2 flex items-center justify-center">
          <Cog class="w-6 h-6 text-white" />
        </div>
        <div>
          <div class="font-bold text-lg leading-tight">检修助手</div>
          <div class="text-[11px] opacity-70 mono">Equipment Maintenance · Mobile</div>
        </div>
      </div>
      <div class="mt-6 text-2xl font-bold leading-tight">{{ title }}</div>
      <div class="mt-1 text-sm opacity-80">车间现场 · 知识检索 · 标准化作业</div>
    </div>

    <!-- 登录表单 -->
    <form v-if="mode === 'login'" @submit.prevent="onLogin" class="px-6 pt-6 space-y-4 flex-1">
      <div class="relative">
        <User class="absolute left-4 top-1/2 -translate-y-1/2 w-5 h-5 text-text-2" />
        <input v-model="username" placeholder="用户名"
               autocomplete="username"
               class="w-full h-14 pl-12 pr-3 rounded-btn border border-border bg-bg text-base outline-none focus:border-accent focus:bg-card" />
      </div>
      <div class="relative">
        <Lock class="absolute left-4 top-1/2 -translate-y-1/2 w-5 h-5 text-text-2" />
        <input v-model="password" type="password" placeholder="密码"
               autocomplete="current-password"
               class="w-full h-14 pl-12 pr-3 rounded-btn border border-border bg-bg text-base outline-none focus:border-accent focus:bg-card" />
      </div>

      <button type="submit" :disabled="loading"
              class="w-full h-14 rounded-btn bg-accent text-white text-base font-semibold ai-shine active:bg-accent-2 disabled:opacity-60">
        {{ loading ? '登录中…' : '登 录' }}
      </button>

      <div class="flex justify-between text-sm pt-2">
        <a class="text-text-2 hover:text-accent">忘记密码?</a>
        <a class="text-accent font-medium" @click="switchTo('register')">立即注册 →</a>
      </div>

    </form>

    <!-- 注册表单 -->
    <form v-else @submit.prevent="onRegister" class="px-6 pt-6 space-y-4 flex-1">
      <div class="relative">
        <User class="absolute left-4 top-1/2 -translate-y-1/2 w-5 h-5 text-text-2" />
        <input v-model="username" placeholder="用户名（至少 3 位）"
               autocomplete="username"
               class="w-full h-14 pl-12 pr-3 rounded-btn border border-border bg-bg text-base outline-none focus:border-accent focus:bg-card" />
      </div>
      <div class="relative">
        <Lock class="absolute left-4 top-1/2 -translate-y-1/2 w-5 h-5 text-text-2" />
        <input v-model="password" type="password" placeholder="密码（至少 6 位）"
               autocomplete="new-password"
               class="w-full h-14 pl-12 pr-3 rounded-btn border border-border bg-bg text-base outline-none focus:border-accent focus:bg-card" />
      </div>
      <div class="relative">
        <Lock class="absolute left-4 top-1/2 -translate-y-1/2 w-5 h-5 text-text-2" />
        <input v-model="confirm" type="password" placeholder="再次输入密码"
               autocomplete="new-password"
               class="w-full h-14 pl-12 pr-3 rounded-btn border border-border bg-bg text-base outline-none focus:border-accent focus:bg-card" />
      </div>
      <div class="text-xs text-text-2 italic">
        注册员工账户；账户角色为一线检修员，如需更高权限请联系管理员。
      </div>

      <button type="submit" :disabled="loading"
              class="w-full h-14 rounded-btn bg-accent text-white text-base font-semibold ai-shine active:bg-accent-2 disabled:opacity-60">
        {{ loading ? '注册中…' : '注 册' }}
      </button>

      <div class="flex justify-between text-sm pt-2">
        <span class="text-text-2">已有账号?</span>
        <a class="text-accent font-medium" @click="switchTo('login')">← 返回登录</a>
      </div>
    </form>

    <div class="text-center text-xs text-text-2 px-6 pb-4 pt-4 mono">
      © 2026 设备检修知识检索系统
    </div>
  </div>
</template>
