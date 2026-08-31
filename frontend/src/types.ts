export type Brand<T, Name extends string> = T & { readonly __brand: Name }
export type ProjectId = Brand<string, 'ProjectId'>
export type VersionId = Brand<string, 'VersionId'>

export interface ProjectVersion {
  id: VersionId
  version: number
  sourceUuid: string
  archiveSize: number
  note: string
  createdAt: string
}

export interface Project {
  id: ProjectId
  sourceUuid: string
  projectName: string
  displayName: string
  note: string
  createdAt: string
  updatedAt: string
  deletedAt: string | null
  versions: ProjectVersion[]
}

export interface DiscoveredProject {
  sourceUuid: string
  projectName: string
  gprjFileName: string
  directory: FileSystemDirectoryHandle
}

export type ModalState =
  | { kind: 'closed' }
  | { kind: 'register' }
  | { kind: 'edit'; project: Project }
  | { kind: 'delete'; project: Project }
  | { kind: 'restore-record'; project: Project }
  | { kind: 'settings' }

export interface RestoreTarget {
  project: Project
  version: ProjectVersion
}
