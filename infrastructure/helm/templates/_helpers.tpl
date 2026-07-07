{{/*
============================================================================
_helpers.tpl — Reusable template definitions for the HR Voice Agent chart
============================================================================
*/}}

{{/* Expand the name of the chart */}}
{{- define "hr-voice-agent.name" -}}
{{- default .Chart.Name .Values.nameOverride | trunc 63 | trimSuffix "-" }}
{{- end }}

{{/* Create a default fully qualified app name */}}
{{- define "hr-voice-agent.fullname" -}}
{{- if .Values.fullnameOverride }}
{{- .Values.fullnameOverride | trunc 63 | trimSuffix "-" }}
{{- else }}
{{- $name := default .Chart.Name .Values.nameOverride }}
{{- if contains $name .Release.Name }}
{{- .Release.Name | trunc 63 | trimSuffix "-" }}
{{- else }}
{{- printf "%s-%s" .Release.Name $name | trunc 63 | trimSuffix "-" }}
{{- end }}
{{- end }}
{{- end }}

{{/* Create chart name and version as used by the chart label */}}
{{- define "hr-voice-agent.chart" -}}
{{- printf "%s-%s" .Chart.Name .Chart.Version | replace "+" "_" | trunc 63 | trimSuffix "-" }}
{{- end }}

{{/* Common labels */}}
{{- define "hr-voice-agent.labels" -}}
helm.sh/chart: {{ include "hr-voice-agent.chart" . }}
app.kubernetes.io/managed-by: {{ .Release.Service }}
app.kubernetes.io/part-of: hr-voice-agent
app.kubernetes.io/version: {{ .Chart.AppVersion | quote }}
{{- end }}

{{/* Selector labels for a specific service component */}}
{{- define "hr-voice-agent.selectorLabels" -}}
app: {{ .component }}
app.kubernetes.io/name: {{ .component }}
app.kubernetes.io/instance: {{ .Release.Name }}
{{- end }}

{{/* Image reference helper */}}
{{- define "hr-voice-agent.image" -}}
{{ .Values.global.imageRegistry }}/{{ .imageName }}:{{ .Values.global.imageTag }}
{{- end }}

{{/* Standard security context for all containers */}}
{{- define "hr-voice-agent.securityContext" -}}
allowPrivilegeEscalation: false
readOnlyRootFilesystem: true
runAsNonRoot: true
runAsUser: 1000
runAsGroup: 1000
capabilities:
  drop: [ALL]
{{- end }}

{{/* Standard pod security context */}}
{{- define "hr-voice-agent.podSecurityContext" -}}
seccompProfile:
  type: RuntimeDefault
fsGroup: 1000
{{- end }}

{{/* Standard probes for a service given its port name */}}
{{- define "hr-voice-agent.probes" -}}
livenessProbe:
  httpGet:
    path: /health
    port: http
  initialDelaySeconds: 15
  periodSeconds: 20
  failureThreshold: 3
readinessProbe:
  httpGet:
    path: /readiness
    port: http
  initialDelaySeconds: 10
  periodSeconds: 10
  failureThreshold: 3
startupProbe:
  httpGet:
    path: /health
    port: http
  failureThreshold: 30
  periodSeconds: 5
{{- end }}
