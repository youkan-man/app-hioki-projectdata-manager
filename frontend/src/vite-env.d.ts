/// <reference types="vite/client" />

interface FileSystemHandlePermissionDescriptor { mode?: 'read' | 'readwrite' }

interface FileSystemHandle {
  readonly kind: 'file' | 'directory'
  readonly name: string
  queryPermission(descriptor?: FileSystemHandlePermissionDescriptor): Promise<PermissionState>
  requestPermission(descriptor?: FileSystemHandlePermissionDescriptor): Promise<PermissionState>
}

interface FileSystemFileHandle extends FileSystemHandle {
  readonly kind: 'file'
  getFile(): Promise<File>
  createWritable(): Promise<FileSystemWritableFileStream>
}

interface FileSystemDirectoryHandle extends FileSystemHandle {
  readonly kind: 'directory'
  entries(): AsyncIterableIterator<[string, FileSystemFileHandle | FileSystemDirectoryHandle]>
  values(): AsyncIterableIterator<FileSystemFileHandle | FileSystemDirectoryHandle>
  getDirectoryHandle(name: string, options?: { create?: boolean }): Promise<FileSystemDirectoryHandle>
  getFileHandle(name: string, options?: { create?: boolean }): Promise<FileSystemFileHandle>
  removeEntry(name: string, options?: { recursive?: boolean }): Promise<void>
}

interface Window {
  showDirectoryPicker?: (options?: { mode?: 'read' | 'readwrite'; startIn?: string }) => Promise<FileSystemDirectoryHandle>
}
