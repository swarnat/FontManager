<template>
  <div class="container">
    <h1 class="mb-4">Font Manager</h1>
    
    <div class="mb-4">
      <label for="previewText" class="form-label">Preview Text:</label>
      <input
        type="text"
        class="form-control"
        id="previewText"
        v-model="previewText"
      >
      <small class="form-text text-muted">
        Font previews use optimized WOFF2 files containing only: a-z A-Z 0-9 öäüß.-_
      </small>
    </div>
    
    <div class="mb-4">
      <label class="form-label">Upload New Fonts:</label>
      <div 
        class="drop-zone"
        :class="{ 'drop-zone-active': isDragging }"
        @dragenter.prevent="isDragging = true"
        @dragover.prevent="isDragging = true"
        @dragleave.prevent="isDragging = false"
        @drop.prevent="handleDrop"
      >
        <div class="drop-zone-content">
          <div v-if="!isDragging">
            <p>Drag and drop font files here</p>
            <p>or</p>
            <label for="fontUpload" class="btn btn-primary">Select Files</label>
          </div>
          <div v-else>
            <p>Drop files to upload</p>
          </div>
        </div>
        <input
          type="file"
          class="visually-hidden"
          id="fontUpload"
          accept=".ttf,.otf"
          multiple
          @change="handleFileUpload"
        >
      </div>
      <div v-if="uploadStatus" class="mt-2" :class="{'text-success': uploadStatus.includes('successful'), 'text-danger': uploadStatus.includes('failed')}">
        {{ uploadStatus }}
      </div>
      <div v-if="uploadProgress.length > 0" class="mt-2">
        <div v-for="(progress, index) in uploadProgress" :key="index" class="mb-1">
          <div>{{ progress.filename }}: {{ progress.status }}</div>
        </div>
      </div>
    </div>
    
    <div class="mb-4">
      <label for="fontSearch" class="form-label">Search Fonts:</label>
      <input
        type="text"
        class="form-control"
        id="fontSearch"
        v-model="searchTerm"
        placeholder="Type to filter font families..."
      >
    </div>
    
    <div v-if="isLoading" class="text-center my-5">
      <div class="spinner-border text-primary" role="status">
        <span class="visually-hidden">Loading...</span>
      </div>
      <p class="mt-2">Loading fonts...</p>
    </div>
    
    <div v-else-if="displayedFonts.length === 0" class="text-center my-5">
      <p>No fonts available. Upload some fonts to get started.</p>
    </div>
    
    <div v-else>
      <div v-for="font in displayedFonts" :key="font.name" class="font-card">
        <div class="card">
          <div class="card-body">
            <h5 class="card-title">{{ font.name }}</h5>
            <div
              class="font-preview"
              :style="{ fontFamily: `${font.name} ${font.default_subfamily.name}` }"
            >
              {{ previewText }}
            </div>
            <div class="text-muted">
              Default style: {{ font.default_subfamily.name }}
            </div>
            <div class="text-muted">
              Available formats:
              <span v-for="file in font.default_subfamily.files" :key="file.path" 
                :class="['badge me-1', file.is_preview ? 'bg-info' : 'bg-secondary']"
                :title="file.is_preview ? 'Preview version with subset of characters' : ''">
                {{ file.type }}{{ file.is_preview ? ' (preview)' : '' }}
              </span>
            </div>
            <button 
              class="btn btn-sm btn-outline-primary mt-2" 
              @click="toggleFontDetails(font)"
            >
              {{ expandedFonts.includes(font.name) ? 'Hide Details' : 'Show All Styles' }}
            </button>
            
            <!-- Subfamily details -->
            <div v-if="expandedFonts.includes(font.name)" class="mt-3">
              <h6>All Styles:</h6>
              <div v-for="subfamily in sortedSubfamilies(font.subfamilies)" :key="subfamily.name" class="subfamily-item mb-3 p-2 border-start border-4">
                <div class="subfamily-name fw-bold">{{ subfamily.name }}</div>
                <div 
                  class="subfamily-preview font-preview"
                  :style="{ fontFamily: `${font.name} ${subfamily.name}` }"
                >
                  {{ previewText }}
                </div>
                <div class="text-muted small">
                  <span v-for="file in subfamily.files" :key="file.path" 
                    :class="['badge me-1', file.is_preview ? 'bg-info' : 'bg-secondary']">
                    {{ file.type }}{{ file.is_preview ? ' (preview)' : '' }}
                  </span>
                </div>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted, onUnmounted, watch, computed } from 'vue'
import axios from 'axios'

interface FontFile {
  path: string;
  type: string;
  is_preview?: boolean;
}

interface Subfamily {
  name: string;
  weight_class?: number;
  files: FontFile[];
}

interface Font {
  name: string;
  subfamilies: Subfamily[];
  default_subfamily: Subfamily;
}

const fonts = ref<Font[]>([])
const displayedFonts = ref<Font[]>([])
const previewText = ref('Zwölf Boxkämpfer jagen Eva quer durch Sylt, während Nick Vodka bei DJ Tom mixt.')
const uploadStatus = ref('')
const isDragging = ref(false)
const uploadProgress = ref<{ filename: string; status: string }[]>([])
const expandedFonts = ref<string[]>([]) // Track which fonts have expanded details
const loadedSubfamilies = ref<Set<string>>(new Set()) // Track which subfamilies have been loaded
const page = ref(1)
const fontsPerPage = 10
const isLoading = ref(false)
const searchTerm = ref('') // Store the search term

const toggleFontDetails = (font: Font) => {
  const index = expandedFonts.value.indexOf(font.name)
  if (index === -1) {
    // Expand the font details
    expandedFonts.value.push(font.name)
    
    // Load all subfamilies for this font if not already loaded
    font.subfamilies.forEach(subfamily => {
      // Skip if it's the default subfamily (already loaded) or if already loaded
      const subfamilyKey = `${font.name}-${subfamily.name}`
      if (subfamily.name === font.default_subfamily.name || loadedSubfamilies.value.has(subfamilyKey)) {
        return
      }
      
      // Load this subfamily's font
      loadSubfamilyFont(font.name, subfamily)
      
      // Mark as loaded
      loadedSubfamilies.value.add(subfamilyKey)
    })
  } else {
    // Collapse the font details
    expandedFonts.value.splice(index, 1)
  }
}

// Helper function to load a subfamily font
const loadSubfamilyFont = (fontName: string, subfamily: Subfamily) => {
  const subPreviewWoff2 = subfamily.files.find(f => f.type === 'woff2' && f.is_preview)
  const subWoff2 = subfamily.files.find(f => f.type === 'woff2' && !f.is_preview)
  const subWoff = subfamily.files.find(f => f.type === 'woff')
  const subTtf = subfamily.files.find(f => f.type === 'ttf')
  
  if (subPreviewWoff2 || subWoff2 || subWoff || subTtf) {
    // Create a unique font face name for this subfamily
    const subfamilyFontName = `${fontName} ${subfamily.name}`
    
    const subfamilyFontFace = new FontFace(subfamilyFontName, `
      local('${subfamilyFontName}'),
      ${subPreviewWoff2 ? `url('${subPreviewWoff2.path}') format('woff2'),` : ''}
      ${!subPreviewWoff2 && subWoff2 ? `url('${subWoff2.path}') format('woff2'),` : ''}
      ${subWoff ? `url('${subWoff.path}') format('woff'),` : ''}
      ${subTtf ? `url('${subTtf.path}') format('truetype')` : ''}
    `.trim())
    
    subfamilyFontFace.load().then(() => {
      document.fonts.add(subfamilyFontFace)
      console.log(`Loaded subfamily font: ${subfamilyFontName}`)
    }).catch(err => {
      console.error(`Error loading subfamily font ${subfamilyFontName}:`, err)
    })
  }
}

// Filtered fonts based on search term
const filteredFonts = computed(() => {
  if (!searchTerm.value.trim()) {
    return fonts.value;
  }
  
  const searchLower = searchTerm.value.toLowerCase().trim();
  return fonts.value.filter(font => 
    font.name.toLowerCase().includes(searchLower)
  );
});

// Function to load more fonts when scrolling
const loadMoreFonts = () => {
  if (isLoading.value) return
  
  const startIndex = (page.value - 1) * fontsPerPage
  const endIndex = startIndex + fontsPerPage
  
  if (startIndex < filteredFonts.value.length) {
    const newFonts = filteredFonts.value.slice(startIndex, endIndex)
    displayedFonts.value = [...displayedFonts.value, ...newFonts]
    
    // Load the default subfamily fonts for the newly added fonts
    newFonts.forEach(font => {
      loadDefaultSubfamilyFont(font)
    })
    
    page.value++
    console.log(`Loaded fonts ${startIndex+1}-${Math.min(endIndex, filteredFonts.value.length)} of ${filteredFonts.value.length}`)
  }
}

// Function to check if we need to load more fonts when scrolling
const handleScroll = () => {
  if (isLoading.value) return
  
  const scrollPosition = window.innerHeight + window.scrollY
  const documentHeight = document.body.offsetHeight
  
  // Load more when user is near the bottom (within 200px)
  if (scrollPosition >= documentHeight - 200) {
    loadMoreFonts()
  }
}

// Helper function to load the default subfamily font
const loadDefaultSubfamilyFont = (font: Font) => {
  const subfamily = font.default_subfamily
  const subfamilyKey = `${font.name}-${subfamily.name}`
  
  // Skip if already loaded
  if (loadedSubfamilies.value.has(subfamilyKey)) {
    return
  }
  
  // Look for preview WOFF2 file first
  const previewWoff2File = subfamily.files.find(f => f.type === 'woff2' && f.is_preview)
  const woff2File = subfamily.files.find(f => f.type === 'woff2' && !f.is_preview)
  const woffFile = subfamily.files.find(f => f.type === 'woff')
  const ttfFile = subfamily.files.find(f => f.type === 'ttf')
  
  if (previewWoff2File || woff2File || woffFile || ttfFile) {
    const subfamilyFontName = `${font.name} ${subfamily.name}`

    const fontFace = new FontFace(subfamilyFontName, `
      local('${subfamilyFontName}'),
      ${previewWoff2File ? `url('${previewWoff2File.path}') format('woff2'),` : ''}
      ${!previewWoff2File && woff2File ? `url('${woff2File.path}') format('woff2'),` : ''}
      ${woffFile ? `url('${woffFile.path}') format('woff'),` : ''}
      ${ttfFile ? `url('${ttfFile.path}') format('truetype')` : ''}
    `.trim())
    
    fontFace.load().then(() => {
      document.fonts.add(fontFace)
      console.log(`Loaded default subfamily font: ${subfamilyFontName}`)
      
      // Mark as loaded
      loadedSubfamilies.value.add(subfamilyKey)
    }).catch(err => {
      console.error(`Error loading default subfamily font ${subfamilyFontName}:`, err)
    })
  }
}

const loadFonts = async () => {
  try {
    isLoading.value = true
    console.log('Fetching fonts from API...')
    
    const response = await axios.get('/api/fonts')
    fonts.value = response.data
    
    console.log(`Fetched ${fonts.value.length} fonts from API`)
    
    // Reset displayed fonts and page
    displayedFonts.value = []
    page.value = 1
    isLoading.value = false
    
    // Reset loaded subfamilies tracking
    loadedSubfamilies.value.clear()
    
    // Load initial batch of fonts
    if (fonts.value.length > 0) {
      console.log('Loading initial batch of fonts...')
      loadMoreFonts()
    } else {
      console.log('No fonts available to display')
    }
  } catch (error: any) {
    console.error('Error loading fonts:', error)
    alert('Failed to load fonts. Please check the console for details.')
  } finally {
    isLoading.value = false
  }
}

const handleDrop = (event: DragEvent) => {
  isDragging.value = false
  if (!event.dataTransfer?.files.length) return
  
  uploadFiles(event.dataTransfer.files)
}

const handleFileUpload = (event: Event) => {
  const input = event.target as HTMLInputElement
  if (!input.files?.length) return
  
  uploadFiles(input.files)
}

// Function to sort subfamilies by weight class (thin to bold)
const sortedSubfamilies = (subfamilies: Subfamily[]) => {
  return [...subfamilies].sort((a, b) => {
    // Default weight class is 400 (Regular) if not specified
    const weightA = a.weight_class || 400;
    const weightB = b.weight_class || 400;
    return weightA - weightB; // Sort from thin to bold
  });
}

const uploadFiles = async (files: FileList) => {
  uploadProgress.value = []
  uploadStatus.value = `Preparing to upload ${files.length} file(s)...`
  
  // Filter out non-font files
  const fontFiles: File[] = []
  for (let i = 0; i < files.length; i++) {
    const file = files[i]
    if (file.name.endsWith('.ttf') || file.name.endsWith('.otf') || file.name.endsWith('.zip')) {
      fontFiles.push(file)
      uploadProgress.value.push({
        filename: file.name,
        status: 'Queued for upload'
      })
    } else {
      uploadProgress.value.push({
        filename: file.name,
        status: 'Skipped (not a font file)'
      })
    }
  }
  
  if (fontFiles.length === 0) {
    uploadStatus.value = 'No valid font files to upload.'
    return
  }
  
  let successCount = 0
  let failCount = 0
  
  // Process files sequentially
  for (let i = 0; i < fontFiles.length; i++) {
    const file = fontFiles[i]
    const index = uploadProgress.value.findIndex(p => p.filename === file.name)
    
    // Update overall status
    uploadStatus.value = `Processing font ${i + 1} of ${fontFiles.length}: ${file.name}`
    
    // Update individual file status
    if (index !== -1) {
      uploadProgress.value[index].status = 'Uploading...'
    }
    
    try {
      // Create a form with just this single file
      const formData = new FormData()
      formData.append('file', file)
      
      // Upload the single file
      await axios.post('/api/fonts/upload', formData, {
        headers: {
          'Content-Type': 'multipart/form-data'
        }
      })
      
      // Update status for this file
      if (index !== -1) {
        uploadProgress.value[index].status = 'Uploaded successfully'
      }
      
      successCount++
      
      // Update overall status after each file is processed
      if (fontFiles.length > 1) {
        uploadStatus.value = `Processed ${i + 1} of ${fontFiles.length} fonts (${successCount} successful, ${failCount} failed)`
      } else {
        uploadStatus.value = 'Font uploaded successfully!'
      }
    } catch (error: any) {
      console.error(`Error uploading font ${file.name}:`, error)
      
      // Update status for this file
      if (index !== -1) {
        let errorMessage = 'Failed to upload'
        if (error.response && error.response.data && error.response.data.detail) {
          errorMessage = `Failed: ${error.response.data.detail}`
        }
        uploadProgress.value[index].status = errorMessage
      }
      
      failCount++
      
      // Update overall status after each file is processed
      uploadStatus.value = `Processed ${i + 1} of ${fontFiles.length} fonts (${successCount} successful, ${failCount} failed)`
    }
  }
  
  // Final status update
  if (fontFiles.length > 1) {
    if (successCount > 0 && failCount === 0) {
      uploadStatus.value = `Successfully uploaded all ${successCount} font(s)!`
    } else if (successCount > 0 && failCount > 0) {
      uploadStatus.value = `Uploaded ${successCount} font(s), but ${failCount} failed.`
    } else {
      uploadStatus.value = `Failed to upload all ${failCount} font(s).`
    }
  }
  
  // Reload fonts to display the newly uploaded ones
  if (successCount > 0) {
    await loadFonts()
  }
}

// Check if the API is reachable
const checkApiConnection = async () => {
  try {
    await axios.get('/api/fonts', { timeout: 5000 })
    return true
  } catch (error: any) {
    console.error('API connection check failed:', error)
    return false
  }
}

// Watch for changes in the search term
watch(searchTerm, () => {
  // Reset displayed fonts and pagination when search term changes
  displayedFonts.value = []
  page.value = 1
  loadMoreFonts()
})

onMounted(async () => {
  // Check API connection first
  const isApiReachable = await checkApiConnection()
  
  if (!isApiReachable) {
    alert('Could not connect to the font API. Please make sure the backend server is running.')
  } else {
    loadFonts()
  }
  
  // Add scroll event listener for infinite scrolling
  window.addEventListener('scroll', handleScroll)
})

// Clean up event listener when component is unmounted
onUnmounted(() => {
  window.removeEventListener('scroll', handleScroll)
})
</script>

<style scoped>
.drop-zone {
  border: 2px dashed #ccc;
  border-radius: 8px;
  padding: 30px;
  text-align: center;
  background-color: #f8f9fa;
  transition: all 0.3s ease;
  cursor: pointer;
}

.drop-zone-active {
  border-color: #007bff;
  background-color: rgba(0, 123, 255, 0.1);
  font-weight:bold;
  color:#777;
  color:25px;
}

.drop-zone-content {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  height:100px;
}

.visually-hidden {
  position: absolute;
  width: 1px;
  height: 1px;
  padding: 0;
  margin: -1px;
  overflow: hidden;
  clip: rect(0, 0, 0, 0);
  white-space: nowrap;
  border: 0;
}

.font-preview {
  font-size: 1.5rem;
  margin: 10px 0;
  line-height: 1.5;
  background-color:#fff;
}

.font-card {
  margin-bottom: 20px;
}

.subfamily-item {
  border-color: #6c757d;
  background-color: #ededed;
  border-radius: 4px;
}

.subfamily-preview {
  font-size: 1.25rem;
  margin: 8px 0;
  line-height: 1.4;
}

.subfamily-name {
  color: #495057;
}
</style>
