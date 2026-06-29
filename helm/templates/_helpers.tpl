{{/* Chart name, reused as the base name for every object. */}}
{{- define "fcs.name" -}}{{ .Chart.Name }}{{- end -}}

{{/* Fully-qualified image ref: repository:tag, defaulting tag to the chart appVersion. */}}
{{- define "fcs.image" -}}
{{- printf "%s:%s" .Values.image.repository (.Values.image.tag | default .Chart.AppVersion) -}}
{{- end -}}

{{/* Common labels applied to every rendered object. */}}
{{- define "fcs.labels" -}}
app.kubernetes.io/name: {{ include "fcs.name" . }}
app.kubernetes.io/managed-by: {{ .Release.Service }}
helm.sh/chart: {{ printf "%s-%s" .Chart.Name .Chart.Version }}
{{- end -}}

{{/* Selector labels — the stable subset used for matchLabels/selectors. */}}
{{- define "fcs.selectorLabels" -}}
app.kubernetes.io/name: {{ include "fcs.name" . }}
{{- end -}}
