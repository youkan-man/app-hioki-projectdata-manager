export type Brand<T, Name extends string> = T & { readonly __brand: Name }
export type ProjectId = Brand<string, 'ProjectId'>
export type VersionId = Brand<string, 'VersionId'>
export type JsonValue = null | boolean | number | string | JsonValue[] | { [key: string]: JsonValue }
export type JsonObject = { [key: string]: JsonValue }

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

export interface ProjectConfiguration {
  filename: string
  version: number
  config: JsonObject
  layoutFilename: string | null
  layout: JsonObject | null
}

export type ModalState =
  | { kind: 'closed' }
  | { kind: 'register' }
  | { kind: 'edit'; project: Project }
  | { kind: 'delete'; project: Project }
  | { kind: 'restore-record'; project: Project }
  | { kind: 'configuration'; project: Project }
  | { kind: 'settings' }

export interface RestoreTarget {
  project: Project
  version: ProjectVersion
}
