"""Standard Helm helper templates for the Kitty chart."""

{{- /*
Expand the name of the chart.
*/}}
{{- define "kitty.name" -}}
{{- default .Chart.Name .Values.nameOverride | trunc 63 | trimSuffix "-" }}
{{- end }}

{{- /*
Create a default fully qualified app name.
We truncate at 63 chars because some Kubernetes name fields are limited to this (by the DNS naming spec).
If release name contains chart name it will be used as a full name.
*/}}
{{- define "kitty.fullname" -}}
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

{{- /*
Create chart name and version as used by the chart label.
*/}}
{{- define "kitty.chart" -}}
{{- printf "%s-%s" .Chart.Name .Chart.Version | replace "+" "_" | trunc 63 | trimSuffix "-" }}
{{- end }}

{{- /*
Common labels
*/}}
{{- define "kitty.labels" -}}
helm.sh/chart: {{ include "kitty.chart" . }}
{{ include "kitty.selectorLabels" . }}
{{- if .Chart.AppVersion }}
app.kubernetes.io/version: {{ .Chart.AppVersion | quote }}
{{- end }}
app.kubernetes.io/managed-by: {{ .Release.Service }}
{{- end }}

{{- /*
Selector labels
*/}}
{{- define "kitty.selectorLabels" -}}
app.kubernetes.io/name: {{ include "kitty.name" . }}
app.kubernetes.io/instance: {{ .Release.Name }}
{{- end }}

{{- /*
Create the name of the service account to use
*/}}
{{- define "kitty.serviceAccountName" -}}
{{- if .Values.serviceAccount.create }}
{{- default (include "kitty.fullname" .) .Values.serviceAccount.name }}
{{- else }}
{{- default "default" .Values.serviceAccount.name }}
{{- end }}
{{- end }}

{{- /*
Create the name of the TLS secret for ingress
*/}}
{{- define "kitty.tlsSecretName" -}}
{{- $tls := first .Values.ingress.tls }}
{{- if $tls }}
{{- $tls.secretName }}
{{- else }}
{{- printf "%s-tls" (include "kitty.fullname" .) }}
{{- end }}
{{- end }}

{{- /*
Return the appropriate OpenTelemetry tracing endpoint based on configuration
*/}}
{{- define "kitty.tracingEndpoint" -}}
{{- if .Values.observability.tracing.enabled }}
{{- .Values.observability.tracing.endpoint }}
{{- else }}
{{- "" }}
{{- end }}
{{- end }}
