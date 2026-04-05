<template>
  <div class="placeholder-page px-4 py-6 md:px-8 md:py-8">
    <section class="placeholder-card">
      <div class="placeholder-icon">
        <UIcon name="i-lucide-shield-question" class="h-8 w-8" />
      </div>
      <h1>对方观点预判</h1>
      <p>功能入口已预留，页面内容暂时留空。</p>
    </section>
  </div>
</template>

<style scoped>
.placeholder-page {
  min-height: 100vh;
  background:
    radial-gradient(circle at top left, rgba(221, 228, 255, 0.7), transparent 26%),
    radial-gradient(circle at bottom right, rgba(244, 234, 216, 0.82), transparent 28%),
    #fcfbf8;
}

.placeholder-card {
  display: flex;
  min-height: calc(100vh - 3rem);
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 14px;
  border-radius: 32px;
  border: 1px solid #ebe5da;
  background: rgba(255, 255, 255, 0.88);
  text-align: center;
  box-shadow: 0 20px 60px rgba(34, 24, 12, 0.06);
  backdrop-filter: blur(12px);
}

.placeholder-icon {
  display: flex;
  height: 72px;
  width: 72px;
  align-items: center;
  justify-content: center;
  border-radius: 24px;
  background: linear-gradient(135deg, #eef2ff, #ffffff);
  color: #3158ff;
}

.placeholder-card h1 {
  font-size: 2rem;
  font-weight: 700;
  color: #18181b;
}

.placeholder-card p {
  font-size: 1rem;
  color: #71717a;
}
</style>
