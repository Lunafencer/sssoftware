<script setup lang="ts">
import { ref, computed } from 'vue'
import { useRouter } from 'vue-router'
import { Lock, User, Loader, Cog, ChevronLeft } from 'lucide-vue-next'
import { useUserStore } from '@/stores/user'
import { showToast, showFailToast } from 'vant'
import { ROLE_LABEL } from '@/utils/permission'

const router = useRouter()
const user = useUserStore()

type Mode = 'login' | 'register'
const mode = ref<Mode>('login')

const username = ref('')
const password = ref('')
const confirm = ref('')
const remember = ref(true)
const loading = ref(false)

const switchTo = (m: Mode) => {
  mode.value = m
  password.value = ''
  confirm.value = ''
  loading.value = false
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
    // 切回登录态，账号回填，密码清空（按 FIX2 流程）
    confirm.value = ''
    password.value = ''
    mode.value = 'login'
  } catch (e: any) {
    showFailToast(e?.message || '注册失败')
  } finally { loading.value = false }
}

const title = computed(() => mode.value === 'login' ? '欢迎回来' : '注册新账号')
const subtitle = computed(() => mode.value === 'login' ? '登录后开始检修工作' : '注册后用账号密码登录系统')
</script>

<template>
  <div class="h-screen w-screen bg-industrial-hero flex items-center justify-center relative overflow-hidden">
    <div class="absolute top-0 inset-x-0 h-12 px-6 flex items-center justify-between text-on-dark z-10">
      <div class="flex items-center gap-3">
        <div class="w-9 h-9 rounded bg-gradient-to-br from-accent to-accent-2 flex items-center justify-center">
          <Cog class="w-5 h-5 text-white" />
        </div>
        <div>
          <div class="font-semibold tracking-wide">设备检修知识检索与作业系统</div>
          <div class="text-[11px] opacity-60 mono">Equipment Maintenance · Multimodal AI</div>
        </div>
      </div>
    </div>

    <!-- 装饰齿轮 -->
    <svg viewBox="0 0 200 200" class="absolute -left-20 -bottom-20 w-[420px] h-[420px] text-white/5">
      <g fill="currentColor">
        <circle cx="100" cy="100" r="60" />
        <circle cx="100" cy="100" r="40" fill="#0B2545" />
        <g v-for="i in 12" :key="i" :transform="`rotate(${i * 30} 100 100)`">
          <rect x="96" y="20" width="8" height="20" />
        </g>
      </g>
    </svg>

    <!-- 卡片 -->
    <div class="w-[420px] industrial-card p-8 relative z-10 shadow-float">
      <!-- 注册时显示返回按钮 -->
      <button v-if="mode === 'register'" type="button" @click="switchTo('login')"
              class="absolute left-4 top-4 w-8 h-8 rounded-full hover:bg-bg flex items-center justify-center text-text-2 hover:text-accent transition">
        <ChevronLeft class="w-4 h-4" />
      </button>

      <div class="text-center mb-6">
        <h1 class="text-2xl font-bold text-primary mb-1">{{ title }}</h1>
        <div class="text-sm text-text-2">{{ subtitle }}</div>
      </div>

      <!-- 登录表单 -->
      <form v-if="mode === 'login'" @submit.prevent="onLogin" class="space-y-4">
        <div class="relative">
          <User class="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-text-2" />
          <input v-model="username" type="text" placeholder="用户名"
                 autocomplete="username"
                 class="w-full h-11 pl-10 pr-3 rounded-btn border border-border bg-bg outline-none focus:border-accent focus:bg-card transition" />
        </div>
        <div class="relative">
          <Lock class="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-text-2" />
          <input v-model="password" type="password" placeholder="密码"
                 autocomplete="current-password"
                 class="w-full h-11 pl-10 pr-3 rounded-btn border border-border bg-bg outline-none focus:border-accent focus:bg-card transition" />
        </div>
        <div class="flex items-center justify-between text-sm">
          <label class="flex items-center gap-2 cursor-pointer text-text-2">
            <input v-model="remember" type="checkbox" class="accent-accent" />
            <span>记住我</span>
          </label>
          <a class="text-accent hover:text-accent-2 cursor-pointer">忘记密码?</a>
        </div>
        <button type="submit" :disabled="loading"
                class="w-full h-11 rounded-btn bg-accent hover:bg-accent-2 text-white font-semibold transition flex items-center justify-center gap-2 disabled:opacity-60 ai-shine">
          <Loader v-if="loading" class="w-4 h-4 animate-spin" />
          <span>{{ loading ? '正在登录…' : '登 录' }}</span>
        </button>
      </form>

      <!-- 注册表单 -->
      <form v-else @submit.prevent="onRegister" class="space-y-4">
        <div class="relative">
          <User class="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-text-2" />
          <input v-model="username" type="text" placeholder="用户名（至少 3 位）"
                 autocomplete="username"
                 class="w-full h-11 pl-10 pr-3 rounded-btn border border-border bg-bg outline-none focus:border-accent focus:bg-card transition" />
        </div>
        <div class="relative">
          <Lock class="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-text-2" />
          <input v-model="password" type="password" placeholder="密码（至少 6 位）"
                 autocomplete="new-password"
                 class="w-full h-11 pl-10 pr-3 rounded-btn border border-border bg-bg outline-none focus:border-accent focus:bg-card transition" />
        </div>
        <div class="relative">
          <Lock class="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-text-2" />
          <input v-model="confirm" type="password" placeholder="再次输入密码"
                 autocomplete="new-password"
                 class="w-full h-11 pl-10 pr-3 rounded-btn border border-border bg-bg outline-none focus:border-accent focus:bg-card transition" />
        </div>
        <div class="text-xs text-text-2 italic">
          注册员工账户；账户角色为一线检修员，如需更高权限请联系管理员。
        </div>
        <button type="submit" :disabled="loading"
                class="w-full h-11 rounded-btn bg-accent hover:bg-accent-2 text-white font-semibold transition flex items-center justify-center gap-2 disabled:opacity-60 ai-shine">
          <Loader v-if="loading" class="w-4 h-4 animate-spin" />
          <span>{{ loading ? '注册中…' : '注 册' }}</span>
        </button>
      </form>

      <div class="mt-6 pt-4 border-t border-border flex items-center justify-between text-sm">
        <span class="text-text-2">{{ mode === 'login' ? '还没有账号?' : '已有账号?' }}</span>
        <a class="text-accent hover:text-accent-2 cursor-pointer font-medium"
           @click="switchTo(mode === 'login' ? 'register' : 'login')">
          {{ mode === 'login' ? '立即注册 →' : '← 返回登录' }}
        </a>
      </div>

    </div>

    <!-- 底部 -->
    <div class="absolute bottom-4 inset-x-0 text-center text-on-dark/60 text-xs mono">
      © 2026 设备检修知识检索系统 · 推荐 Chrome 100+
    </div>
  </div>
</template>

<style scoped>
.fade-enter-active, .fade-leave-active { transition: opacity .15s, transform .15s; }
.fade-enter-from, .fade-leave-to { opacity: 0; transform: translateY(-4px); }
</style>
