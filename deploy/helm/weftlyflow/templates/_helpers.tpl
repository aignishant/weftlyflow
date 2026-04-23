{{/*
_helpers.tpl — Named templates shared across all Weftlyflow chart templates.

Every helper follows the Helm convention of being prefixed with the chart name
so they do not collide when this chart is used as a sub-chart.
*/}}

{{/*
Expand the name of the chart. Truncated to 63 chars (Kubernetes label limit).
*/}}
{{- define "weftlyflow.name" -}}
{{- default .Chart.Name .Values.nameOverride | trunc 63 | trimSuffix "-" }}
{{- end }}

{{/*
Create a default fully-qualified app name.
We truncate at 63 chars because some Kubernetes name fields are limited.
If release name already contains the chart name it is used as-is.
*/}}
{{- define "weftlyflow.fullname" -}}
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

{{/*
Chart label: name-version.
*/}}
{{- define "weftlyflow.chart" -}}
{{- printf "%s-%s" .Chart.Name .Chart.Version | replace "+" "_" | trunc 63 | trimSuffix "-" }}
{{- end }}

{{/*
Common labels applied to every resource.
*/}}
{{- define "weftlyflow.labels" -}}
helm.sh/chart: {{ include "weftlyflow.chart" . }}
{{ include "weftlyflow.selectorLabels" . }}
{{- if .Chart.AppVersion }}
app.kubernetes.io/version: {{ .Chart.AppVersion | quote }}
{{- end }}
app.kubernetes.io/managed-by: {{ .Release.Service }}
{{- end }}

{{/*
Selector labels — stable subset used in matchLabels (must not change across upgrades).
*/}}
{{- define "weftlyflow.selectorLabels" -}}
app.kubernetes.io/name: {{ include "weftlyflow.name" . }}
app.kubernetes.io/instance: {{ .Release.Name }}
{{- end }}

{{/*
ServiceAccount name.
*/}}
{{- define "weftlyflow.serviceAccountName" -}}
{{- if .Values.serviceAccount.create }}
{{- default (include "weftlyflow.fullname" .) .Values.serviceAccount.name }}
{{- else }}
{{- default "default" .Values.serviceAccount.name }}
{{- end }}
{{- end }}

{{/*
Resolve the image reference for a given component ("api", "worker", "beat").
Usage: {{ include "weftlyflow.image" (dict "component" "api" "Values" .Values "Chart" .Chart) }}
*/}}
{{- define "weftlyflow.image" -}}
{{- $tag := .Values.image.tag | default .Chart.AppVersion }}
{{- printf "%s/%s/%s:%s" .Values.image.registry .Values.image.repositoryPrefix .component $tag }}
{{- end }}

{{/*
Name of the Secret that holds sensitive env vars. Returns the user-supplied
existingSecret name when set, otherwise the chart-managed secret name.
*/}}
{{- define "weftlyflow.secretName" -}}
{{- if .Values.existingSecret }}
{{- .Values.existingSecret }}
{{- else }}
{{- printf "%s-secrets" (include "weftlyflow.fullname" .) }}
{{- end }}
{{- end }}

{{/*
Name of the ConfigMap for non-sensitive settings.
*/}}
{{- define "weftlyflow.configMapName" -}}
{{- printf "%s-config" (include "weftlyflow.fullname" .) }}
{{- end }}

{{/*
Construct the PostgreSQL DSN from the bitnami sub-chart values.
Used only when postgresql.enabled is true and secrets.databaseUrl is empty.
*/}}
{{- define "weftlyflow.postgresqlUrl" -}}
{{- $host := printf "%s-postgresql" .Release.Name }}
{{- $user := .Values.postgresql.auth.username | default "weftlyflow" }}
{{- $pass := .Values.postgresql.auth.password | default "weftlyflow" }}
{{- $db   := .Values.postgresql.auth.database  | default "weftlyflow" }}
{{- printf "postgresql+psycopg://%s:%s@%s:5432/%s" $user $pass $host $db }}
{{- end }}

{{/*
Construct the Redis base URL from the bitnami sub-chart values.
Used only when redis.enabled is true and secrets.redisUrl is empty.
*/}}
{{- define "weftlyflow.redisUrl" -}}
{{- $host := printf "%s-redis-master" .Release.Name }}
{{- printf "redis://%s:6379/0" $host }}
{{- end }}

{{/*
Resolve the DATABASE_URL value:
  priority: secrets.databaseUrl > externalDatabase.url > auto-constructed from sub-chart
*/}}
{{- define "weftlyflow.databaseUrl" -}}
{{- if .Values.secrets.databaseUrl }}
{{- .Values.secrets.databaseUrl }}
{{- else if .Values.externalDatabase.url }}
{{- .Values.externalDatabase.url }}
{{- else }}
{{- include "weftlyflow.postgresqlUrl" . }}
{{- end }}
{{- end }}

{{/*
Resolve the REDIS_URL:
  priority: secrets.redisUrl > externalRedis.url > auto-constructed
*/}}
{{- define "weftlyflow.resolvedRedisUrl" -}}
{{- if .Values.secrets.redisUrl }}
{{- .Values.secrets.redisUrl }}
{{- else if .Values.externalRedis.url }}
{{- .Values.externalRedis.url }}
{{- else }}
{{- include "weftlyflow.redisUrl" . }}
{{- end }}
{{- end }}

{{/*
Resolve CELERY_BROKER_URL (defaults to redis db 0).
*/}}
{{- define "weftlyflow.celeryBrokerUrl" -}}
{{- if .Values.secrets.celeryBrokerUrl }}
{{- .Values.secrets.celeryBrokerUrl }}
{{- else if .Values.externalRedis.url }}
{{- .Values.externalRedis.url }}
{{- else }}
{{- $host := printf "%s-redis-master" .Release.Name }}
{{- printf "redis://%s:6379/0" $host }}
{{- end }}
{{- end }}

{{/*
Resolve CELERY_RESULT_BACKEND (defaults to redis db 1).
*/}}
{{- define "weftlyflow.celeryResultBackend" -}}
{{- if .Values.secrets.celeryResultBackend }}
{{- .Values.secrets.celeryResultBackend }}
{{- else if .Values.externalRedis.url }}
{{- /* Replace trailing /0 with /1 if present, otherwise append /1 */}}
{{- .Values.externalRedis.url | replace "/0" "/1" }}
{{- else }}
{{- $host := printf "%s-redis-master" .Release.Name }}
{{- printf "redis://%s:6379/1" $host }}
{{- end }}
{{- end }}

{{/*
Shared envFrom block — ConfigMap + Secret — used in all three Deployments
and the migration Job. Accepts the top-level dot context.
*/}}
{{- define "weftlyflow.envFrom" -}}
- configMapRef:
    name: {{ include "weftlyflow.configMapName" . }}
- secretRef:
    name: {{ include "weftlyflow.secretName" . }}
{{- range .Values.extraEnvFrom }}
- {{ toYaml . | nindent 2 | trim }}
{{- end }}
{{- end }}
