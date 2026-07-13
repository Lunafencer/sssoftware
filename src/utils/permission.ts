import {
  type FrontendRole,
  type Role,
  ROLE_LABEL,
  mapBackendRole,
  mapFrontendRole,
  ASSIGNABLE_ROLES,
  isAuditorRole,
} from '@/constants/roles'

// 兼容旧引用：从单一来源 re-export（FIX5 第 17 项）
export type { Role, FrontendRole }
export { ROLE_LABEL, mapBackendRole, mapFrontendRole, ASSIGNABLE_ROLES, isAuditorRole }

export interface MenuItem {
  path: string
  label: string
  roles?: Role[]
  badge?: number
  highlight?: boolean
}

/** 全局菜单清单,移动端与 PC 端通过该清单 + 当前角色派生可见项
 *  排序按功能类别（不显示分类标签）：
 *    1) 日常使用：检索 / 作业指引 / 知识图谱
 *    2) 知识库：浏览 / 上传 / 待审核 / 知识库管理
 *    3) 系统管理：用户管理
 *    4) 个人：历史与收藏 / 个人中心
 */
export const MENU_ITEMS: MenuItem[] = [
  // —— 日常使用 ——
  { path: '/search',            label: '知识检索', highlight: true },
  { path: '/workflow',          label: '作业指引' },
  { path: '/kg',                label: '知识图谱' },
  // —— 知识库 ——
  // FIX6 第 1 项：显式声明知识库浏览对一线员工、审查员、管理员均可见
  { path: '/knowledge/browse',  label: '知识库',     roles: ['frontline', 'auditor', 'admin'] },
  // FIX7 第 3 项：经验分享 / 知识上传对前端/审查员/管理员均开放，后端按角色决定是否入审核队列
  { path: '/knowledge/upload',  label: '知识上传',   roles: ['frontline', 'auditor', 'admin'] },
  { path: '/auditor/review',    label: '待审核',     roles: ['auditor', 'admin'] },
  { path: '/auditor/knowledge', label: '知识库管理', roles: ['auditor', 'admin'] },
  // —— 系统管理 ——
  { path: '/admin/user',        label: '用户管理',   roles: ['admin'] },
  // —— 个人 ——
  { path: '/history',           label: '历史与收藏' },
  { path: '/profile',           label: '个人中心' },
]

/** 权限判断:无 allow 视为公共菜单 */
export function hasPermission(current: Role | undefined, allow?: Role[]): boolean {
  if (!allow || allow.length === 0) return true
  if (!current) return false
  return allow.includes(current)
}

export function hasRole(current: Role | undefined, allow: Role[]): boolean {
  return hasPermission(current, allow)
}

/** 根据当前角色获取可见菜单 */
export function getVisibleMenuItems(role: Role | undefined): MenuItem[] {
  return MENU_ITEMS.filter(it => hasPermission(role, it.roles))
}
