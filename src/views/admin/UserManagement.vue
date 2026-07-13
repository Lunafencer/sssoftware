<script setup lang="ts">
/**
 * 用户管理（FIX4 第 4 项）— 独立页面 /admin/users
 *  仅 admin 可见（在 router 守卫处由 meta.roles=['admin'] 拦截）。
 *  - 真实数据来源：GET /api/admin/users
 *  - 角色变更：PUT /api/admin/users/{id}/role
 *  - 与 admin/Pc.vue 内置的 user tab 共享同一份组件逻辑
 */
import Pc from './Pc.vue'
</script>

<template>
  <Pc />
</template>
