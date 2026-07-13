<script setup lang="ts">
import { useRoute, useRouter } from 'vue-router'
import { ChevronLeft, Heart, Copy, MessageCircle, Book } from 'lucide-vue-next'
import { useDevice } from '@/composables/useDevice'
import StatusTag from '@/components/common/StatusTag.vue'
import SimilarityBar from '@/components/common/SimilarityBar.vue'

const route = useRoute()
const router = useRouter()
const { isPC } = useDevice()

const detail = {
  id: route.params.id,
  title: '热轧主电机异响处理案例 #2024-031',
  type: 'case' as const,
  similarity: 0.92,
  source: '王师傅提交 · 2024-03-15',
  device: 'YKK630-4',
  body: `### 故障现象
检修员发现主电机驱动端轴承温度异常上升至 78℃,伴随金属摩擦声,持续约 4 小时。

### 处理过程
1. 立即按 SOP §4.3 流程停机,执行 LOTO 锁定
2. 等待电机自然冷却至 40℃ 以下,使用红外测温仪复测
3. 拆卸驱动端端盖,目视检查滚动体与保持架
4. 发现保持架轻微变形,滚动体表面有点蚀剥落
5. 更换轴承,清洗轴承腔,填充 Mobil Polyrex EM 润滑脂
6. 装复后通电试运行 10 分钟,振动速度 3.2mm/s,温升 28K,无异响

### 经验总结
- 轴承点蚀往往与润滑脂污染或寿命到期有关
- 建议建立按里程的预防性更换制度
- 拆卸时务必使用专用拉马,严禁锤击`
}
</script>

<template>
  <div :class="isPC ? 'p-6 max-w-5xl mx-auto' : 'h-full flex flex-col'">
    <!-- 顶栏 -->
    <header v-if="!isPC" class="flex-shrink-0 h-12 bg-card border-b border-border flex items-center px-2">
      <button @click="router.back()" class="w-10 h-10 flex items-center justify-center"><ChevronLeft class="w-5 h-5" /></button>
      <span class="flex-1 text-center font-semibold truncate">{{ detail.title }}</span>
      <span class="w-10"></span>
    </header>

    <div :class="isPC ? '' : 'flex-1 overflow-auto'">
      <div class="industrial-card p-6" :class="isPC ? '' : 'rounded-none border-x-0'">
        <button v-if="isPC" @click="router.back()" class="text-sm text-text-2 hover:text-accent mb-3 inline-flex items-center gap-1">
          <ChevronLeft class="w-4 h-4" /> 返回结果列表
        </button>
        <div class="flex flex-wrap items-start gap-3 mb-4">
          <StatusTag :type="detail.type" />
          <h1 class="text-xl md:text-2xl font-bold flex-1 min-w-0">{{ detail.title }}</h1>
          <div class="w-44">
            <div class="text-xs text-text-2 mb-1">相似度</div>
            <SimilarityBar :value="detail.similarity" />
          </div>
        </div>
        <div class="text-sm text-text-2 flex items-center gap-3 flex-wrap">
          <span class="inline-flex items-center gap-1"><Book class="w-3.5 h-3.5" />{{ detail.source }}</span>
          <span class="mono px-2 py-0.5 rounded bg-bg">{{ detail.device }}</span>
        </div>

        <!-- Markdown body (简单 split 渲染) -->
        <article class="mt-6 leading-7 whitespace-pre-wrap">{{ detail.body }}</article>

        <!-- 案例图片占位 -->
        <div class="mt-5 grid grid-cols-3 gap-2">
          <div v-for="i in 3" :key="i" class="aspect-video bg-bg rounded-card border border-border flex items-center justify-center text-text-2 text-xs">现场照片 {{ i }}</div>
        </div>

        <div class="mt-6 pt-4 border-t border-border flex items-center gap-3 text-sm">
          <button class="text-text-2 hover:text-success">👍 有帮助</button>
          <button class="text-text-2 hover:text-danger">👎 不准确</button>
          <span class="ml-auto text-xs text-text-2 mono">案例 ID: {{ detail.id }}</span>
        </div>
      </div>
    </div>

    <!-- 底部操作栏 -->
    <footer class="flex-shrink-0 h-14 border-t border-border bg-card flex items-center px-3 gap-2"
            :class="isPC ? 'mt-4 industrial-card !h-14 px-4' : 'safe-bottom'">
      <button class="flex-1 h-10 rounded-btn bg-bg flex items-center justify-center gap-1 text-sm"><Heart class="w-4 h-4" /> 收藏</button>
      <button class="flex-1 h-10 rounded-btn bg-bg flex items-center justify-center gap-1 text-sm"><Copy class="w-4 h-4" /> 复制</button>
      <button class="flex-1 h-10 rounded-btn bg-accent text-white flex items-center justify-center gap-1 text-sm font-semibold">
        <MessageCircle class="w-4 h-4" /> 以此继续提问
      </button>
    </footer>
  </div>
</template>
