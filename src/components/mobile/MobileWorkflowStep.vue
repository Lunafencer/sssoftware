<script setup lang="ts">
import type { SopStep } from '@/api/workflow'
import { AlertTriangle, Clock, Wrench, BookOpen } from 'lucide-vue-next'

defineProps<{ step: SopStep; checks: boolean[]; index: number; total: number }>()
defineEmits<{ (e: 'toggle', i: number): void }>()
</script>

<template>
  <div class="px-4 pt-3 pb-3">
    <!-- 步骤标题 -->
    <div class="flex items-center gap-2 mb-2">
      <span class="mono text-sm text-text-2">{{ index + 1 }} / {{ total }}</span>
      <h2 class="text-[22px] font-bold leading-tight flex-1">{{ step.name }}</h2>
    </div>

    <div class="flex items-center gap-3 text-text-2 text-sm mb-3">
      <span class="inline-flex items-center gap-1"><Clock class="w-4 h-4" />预计 {{ step.estMinutes }} 分钟</span>
    </div>

    <!-- 危险条 -->
    <div v-if="step.hazardous"
         class="hazard-stripe mb-3 px-3 py-2 rounded-card border border-warning/40 flex items-center gap-2 text-warning font-medium">
      <AlertTriangle class="w-5 h-5" /> 危险作业 · 请严格执行 LOTO 与安全规程
    </div>

    <!-- 描述 -->
    <p class="text-base leading-relaxed text-text mb-4">{{ step.desc }}</p>

    <!-- 工具 / 物料 / 手册 -->
    <div v-if="step.tools?.length || step.materials?.length || step.manualRef" class="industrial-card p-3 mb-4 space-y-2 text-sm">
      <div v-if="step.tools?.length" class="flex items-start gap-2">
        <Wrench class="w-4 h-4 mt-0.5 text-text-2" />
        <span class="text-text-2 mr-1">工具:</span>
        <span>{{ step.tools.join(' · ') }}</span>
      </div>
      <div v-if="step.materials?.length" class="flex items-start gap-2">
        <span class="w-4 h-4 mt-0.5 inline-block">📦</span>
        <span class="text-text-2 mr-1">物料:</span>
        <span>{{ step.materials.join(' · ') }}</span>
      </div>
      <div v-if="step.manualRef" class="flex items-start gap-2">
        <BookOpen class="w-4 h-4 mt-0.5 text-text-2" />
        <span class="text-text-2 mr-1">参考:</span>
        <span class="text-accent">{{ step.manualRef }}</span>
      </div>
    </div>

    <!-- 大复选框 -->
    <div class="space-y-2">
      <label v-for="(cp, i) in step.checkPoints" :key="i"
             class="flex items-start gap-3 p-3 industrial-card cursor-pointer active:bg-bg">
        <input type="checkbox" :checked="checks[i]" @change="$emit('toggle', i)"
               class="w-6 h-6 mt-0.5 accent-accent flex-shrink-0" />
        <span class="text-base leading-snug">{{ cp }}</span>
      </label>
    </div>
  </div>
</template>
