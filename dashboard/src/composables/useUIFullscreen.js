import { ref } from 'vue'

// Shared singleton — CameraView set, App.vue read
export const isUIFullscreen = ref(false)
