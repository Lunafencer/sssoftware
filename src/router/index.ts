import { createRouter, createWebHashHistory, type RouteRecordRaw } from 'vue-router'
import { useUserStore } from '@/stores/user'
import { showToast } from 'vant'

const routes: RouteRecordRaw[] = [
  { path: '/login',     component: () => import('@/views/login/index.vue'),     meta: { layout: 'blank', title: '登录' } },

  // 首页 = 多模态检索
  { path: '/',          redirect: '/search' },

  // 检索
  { path: '/search',    component: () => import('@/views/search/index.vue'),    meta: { layout: 'app', title: '知识检索' } },
  { path: '/search/:id',component: () => import('@/views/search/Detail.vue'),   meta: { layout: 'app', title: '检索详情' } },

  // 历史详情
  { path: '/history/:id', component: () => import('@/views/history/Detail.vue'), meta: { layout: 'app', title: '历史详情' } },

  // 工单 / 作业指引
  { path: '/workflow',  component: () => import('@/views/workflow/index.vue'),  meta: { layout: 'app', title: '作业指引' } },
  { path: '/workflow/:id', component: () => import('@/views/workflow/Detail.vue'), meta: { layout: 'app', title: '作业指引详情' } },

  // 知识库浏览（FIX6 第 1 项：三种角色均可只读浏览）
  { path: '/knowledge/browse', component: () => import('@/views/knowledge/Browse.vue'),
    meta: { layout: 'app', title: '知识库', roles: ['frontline', 'auditor', 'admin'] } },
  // 员工经验分享上传（FIX7 第 3 项：前端/审查员/管理员均可进入，提交后按角色决定是否走审核）
  { path: '/knowledge/upload', component: () => import('@/views/knowledge/Upload.vue'), meta: { layout: 'app', title: '知识上传', roles: ['frontline', 'auditor', 'admin'] } },
  { path: '/kb/preview/:docId', component: () => import('@/views/knowledge/Preview.vue'),
    meta: { layout: 'app', title: '文档预览', roles: ['frontline', 'auditor', 'admin'] } },

  // 审查员：待审核列表
  { path: '/auditor/review', component: () => import('@/views/audit/KnowledgeReview.vue'),
    meta: { layout: 'app', title: '待审核', roles: ['auditor', 'admin'] } },
  // 审查员 / 管理员：知识库管理
  { path: '/auditor/knowledge', component: () => import('@/views/knowledge/KnowledgeManage.vue'),
    meta: { layout: 'app', title: '知识库管理', roles: ['auditor', 'admin'] } },
  // 管理员知识库管理（兼容旧路径）
  { path: '/admin/knowledge', redirect: '/auditor/knowledge' },

  // 知识图谱
  { path: '/kg',        component: () => import('@/views/kg/index.vue'),        meta: { layout: 'app', title: '知识图谱' } },

  // 历史 / 我的
  { path: '/history',   component: () => import('@/views/history/index.vue'),   meta: { layout: 'app', title: '历史与收藏' } },
  { path: '/profile',   component: () => import('@/views/profile/index.vue'),   meta: { layout: 'app', title: '用户中心' } },

  // 旧入口重定向
  { path: '/workspace', redirect: '/search' },
  { path: '/dashboard', redirect: '/search' },
  { path: '/audit',     redirect: '/auditor/review' },
  { path: '/audit/knowledge', redirect: '/auditor/review' },

  // 系统管理（用户管理）
  { path: '/admin/user', component: () => import('@/views/admin/index.vue'), meta: { layout: 'app', title: '用户管理', roles: ['admin'] } },
  { path: '/admin/:sub?', component: () => import('@/views/admin/index.vue'),   meta: { layout: 'app', title: '系统管理', roles: ['admin'], mobileReadonly: true } },

  { path: '/:pathMatch(.*)*', redirect: '/search' }
]

const router = createRouter({
  history: createWebHashHistory(),
  routes,
  scrollBehavior: () => ({ top: 0 })
})

router.beforeEach(async (to, _from, next) => {
  const u = useUserStore()
  document.title = `${to.meta?.title || ''} · 设备检修知识检索系统`

  if (to.path !== '/login' && !u.isLoggedIn) {
    return next('/login')
  }
  // 已登录但用户信息尚未回填（刷新后），先 hydrate 以便角色守卫生效
  if (u.isLoggedIn && !u.info) {
    await u.hydrate()
    if (!u.isLoggedIn) return next('/login')
  }
  // 角色守卫
  const allowed = (to.meta?.roles as string[]) || []
  if (allowed.length && !allowed.includes(u.role)) {
    showToast('权限不足,无法访问该模块')
    return next('/')
  }
  if (to.meta?.mobileReadonly && window.innerWidth < 1024) {
    showToast({ message: '该模块在移动端仅可只读浏览,完整操作请前往 PC 端', duration: 2500 })
  }
  next()
})

export default router
