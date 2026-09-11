$ErrorActionPreference = "Stop"

$Repo = (git rev-parse --show-toplevel).Trim()
if (-not $Repo) { throw "Lancer ce script depuis un dépôt Git." }

$Repo = (Resolve-Path $Repo).Path
$Parent = Split-Path -Parent $Repo
$WorktreeRoot = Join-Path $Parent "INIS-worktrees"

$agents = @(
    @{ Name = "codex"; Branch = "agent/codex/domain" },
    @{ Name = "devin"; Branch = "agent/devin/storage" },
    @{ Name = "opencode"; Branch = "agent/opencode/messaging" },
    @{ Name = "antigravity"; Branch = "agent/antigravity/api" },
    @{ Name = "cursor"; Branch = "agent/cursor/integration" }
)

New-Item -ItemType Directory -Force -Path $WorktreeRoot | Out-Null
git fetch origin --prune

foreach ($a in $agents) {
    $path = Join-Path $WorktreeRoot $a.Name
    $branch = $a.Branch

    if (Test-Path $path) {
        Write-Host "EXISTS $path" -ForegroundColor Yellow
        continue
    }

    git show-ref --verify --quiet "refs/heads/$branch"
    if ($LASTEXITCODE -eq 0) {
        git worktree add $path $branch
    } else {
        git worktree add -b $branch $path main
    }

    if ($LASTEXITCODE -ne 0) {
        throw "Impossible de créer $path"
    }

    Write-Host "CREATED $path -> $branch" -ForegroundColor Green
}

git worktree list
