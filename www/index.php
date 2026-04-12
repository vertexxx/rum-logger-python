<?php
$onlineThresholdSeconds = 60;

function escape_html($value)
{
    return htmlspecialchars((string) $value, ENT_QUOTES, 'UTF-8');
}

function normalize_device_query($deviceQuery)
{
    $deviceQuery = trim(str_replace("\0", '', (string) $deviceQuery));
    return basename($deviceQuery);
}

function get_device_file_name($deviceName)
{
    if (pathinfo($deviceName, PATHINFO_EXTENSION) !== 'json') {
        return $deviceName . '.json';
    }

    return $deviceName;
}

function format_time_delta($timeDifference, $onlineThresholdSeconds)
{
    if ($timeDifference > $onlineThresholdSeconds) {
        return '>' . $onlineThresholdSeconds . ' seconds';
    }

    return $timeDifference . ' seconds';
}

function get_device_meta($fileName, $onlineThresholdSeconds)
{
    $lastModified = filemtime($fileName);
    $timeDifference = max(0, time() - $lastModified);

    return array(
        'file' => $fileName,
        'device' => pathinfo($fileName, PATHINFO_FILENAME),
        'lastModified' => $lastModified,
        'timeDifference' => $timeDifference,
        'timeDelta' => format_time_delta($timeDifference, $onlineThresholdSeconds),
        'isOnline' => $timeDifference < $onlineThresholdSeconds,
    );
}

function get_device_list($onlineThresholdSeconds)
{
    $devices = array();
    $files = glob('*.json');

    if ($files === false) {
        return $devices;
    }

    sort($files, SORT_NATURAL | SORT_FLAG_CASE);

    foreach ($files as $fileName) {
        if ($fileName === 'manifest.json' || !is_file($fileName)) {
            continue;
        }

        $devices[] = get_device_meta($fileName, $onlineThresholdSeconds);
    }

    return $devices;
}

$requestedDevice = isset($_GET['device']) ? normalize_device_query($_GET['device']) : null;
$deviceList = get_device_list($onlineThresholdSeconds);
?>
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <title>R.U.M. Logger</title>
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <meta name="theme-color" content="#070b16">
    <link rel="manifest" href="manifest.json">
    <link rel="icon" type="image/png" href="icon.png">
    <style>
        :root {
            --bg: #070b16;
            --panel: rgba(12, 18, 34, 0.84);
            --panel-strong: rgba(9, 14, 28, 0.95);
            --line: rgba(74, 245, 214, 0.24);
            --text: #eafcff;
            --muted: #87a2bb;
            --muted-strong: #6a7384;
            --cyan: #41f5de;
            --pink: #ff4fd8;
            --lime: #76ff7a;
            --amber: #ffd166;
            --red: #ff6b8c;
            --offline: #7f8797;
            --shadow-cyan: 0 0 24px rgba(65, 245, 222, 0.28);
            --shadow-pink: 0 0 30px rgba(255, 79, 216, 0.2);
            --radius: 22px;
        }

        * {
            box-sizing: border-box;
        }

        body {
            margin: 0;
            min-height: 100vh;
            color: var(--text);
            font-family: "Trebuchet MS", "Segoe UI", sans-serif;
            background:
                radial-gradient(circle at top left, rgba(255, 79, 216, 0.18), transparent 24%),
                radial-gradient(circle at top right, rgba(65, 245, 222, 0.16), transparent 22%),
                linear-gradient(145deg, #05070e 0%, #09101d 48%, #05070f 100%);
            text-align: center;
            padding: 28px 18px 48px;
        }

        body::before,
        body::after {
            content: "";
            position: fixed;
            inset: auto;
            width: 42vw;
            height: 42vw;
            border-radius: 50%;
            filter: blur(90px);
            pointer-events: none;
            opacity: 0.28;
            z-index: 0;
        }

        body::before {
            top: -10vw;
            left: -8vw;
            background: rgba(255, 79, 216, 0.3);
        }

        body::after {
            right: -12vw;
            bottom: -10vw;
            background: rgba(65, 245, 222, 0.24);
        }

        .shell {
            position: relative;
            z-index: 1;
            width: min(980px, 100%);
            margin: 0 auto;
            padding: 28px 18px 32px;
            border: 1px solid var(--line);
            border-radius: calc(var(--radius) + 6px);
            background: linear-gradient(180deg, rgba(8, 12, 24, 0.92), rgba(8, 12, 24, 0.72));
            box-shadow: var(--shadow-cyan), var(--shadow-pink), inset 0 0 0 1px rgba(255, 255, 255, 0.03);
            backdrop-filter: blur(14px);
        }

        .hero {
            margin-bottom: 24px;
        }

        .hero img {
            width: min(360px, 72vw);
            max-width: 100%;
            height: auto;
            filter: drop-shadow(0 0 24px rgba(65, 245, 222, 0.24));
        }

        .eyebrow {
            margin: 16px 0 6px;
            color: var(--cyan);
            font-size: 0.78rem;
            letter-spacing: 0.36rem;
            text-transform: uppercase;
            text-shadow: 0 0 14px rgba(65, 245, 222, 0.35);
        }

        h1 {
            margin: 0;
            font-family: "Courier New", Courier, monospace;
            font-size: clamp(1.8rem, 4vw, 3rem);
            letter-spacing: 0.08em;
            text-transform: uppercase;
            text-shadow: 0 0 18px rgba(65, 245, 222, 0.24), 0 0 32px rgba(255, 79, 216, 0.16);
        }

        .subtitle,
        #countdown {
            color: var(--muted);
        }

        .subtitle {
            margin: 12px auto 0;
            width: min(680px, 100%);
            line-height: 1.6;
        }

        #countdown {
            margin: 18px 0 0;
            font-size: 0.95rem;
            letter-spacing: 0.04em;
        }

        .divider {
            width: min(760px, 100%);
            height: 1px;
            margin: 24px auto;
            background: linear-gradient(90deg, transparent, rgba(65, 245, 222, 0.72), rgba(255, 79, 216, 0.72), transparent);
            box-shadow: 0 0 18px rgba(65, 245, 222, 0.35);
        }

        .device-list,
        .status-list,
        .image-grid {
            list-style: none;
            padding: 0;
            margin: 0;
        }

        .device-list {
            display: grid;
            gap: 16px;
        }

        .device-card {
            display: block;
            text-align: left;
            padding: 18px 20px;
            border-radius: var(--radius);
            text-decoration: none;
            color: var(--text);
            background: linear-gradient(180deg, rgba(10, 17, 31, 0.95), rgba(8, 12, 22, 0.92));
            border: 1px solid rgba(65, 245, 222, 0.14);
            box-shadow: inset 0 0 0 1px rgba(255, 255, 255, 0.02), 0 16px 34px rgba(0, 0, 0, 0.3);
            transition: transform 0.18s ease, border-color 0.18s ease, box-shadow 0.18s ease;
        }

        .device-card:hover {
            transform: translateY(-2px);
            border-color: rgba(65, 245, 222, 0.4);
            box-shadow: inset 0 0 0 1px rgba(65, 245, 222, 0.08), 0 0 22px rgba(65, 245, 222, 0.12), 0 16px 34px rgba(0, 0, 0, 0.34);
        }

        .device-card.is-offline {
            color: var(--offline);
            border-color: rgba(127, 135, 151, 0.24);
            background: linear-gradient(180deg, rgba(15, 17, 24, 0.94), rgba(10, 12, 18, 0.9));
        }

        .device-card.is-offline .device-name {
            text-decoration: line-through;
        }

        .device-name-row,
        .detail-heading {
            display: flex;
            align-items: center;
            justify-content: center;
            gap: 10px;
            flex-wrap: wrap;
        }

        .device-name-row {
            justify-content: flex-start;
        }

        .device-name {
            font-size: 1.1rem;
            font-weight: 700;
            letter-spacing: 0.04em;
        }

        .status-dot {
            width: 12px;
            height: 12px;
            border-radius: 999px;
            flex: 0 0 12px;
            background: var(--offline);
        }

        .status-dot.is-online {
            background: var(--lime);
            box-shadow: 0 0 8px rgba(118, 255, 122, 0.75), 0 0 18px rgba(118, 255, 122, 0.42);
        }

        .device-meta {
            margin-top: 10px;
            display: flex;
            gap: 18px;
            flex-wrap: wrap;
            color: var(--muted);
            font-size: 0.92rem;
        }

        .device-card.is-offline .device-meta {
            color: var(--muted-strong);
        }

        .chip {
            display: inline-flex;
            align-items: center;
            justify-content: center;
            gap: 8px;
            padding: 8px 12px;
            border-radius: 999px;
            border: 1px solid rgba(65, 245, 222, 0.22);
            background: rgba(65, 245, 222, 0.08);
            color: var(--cyan);
            text-transform: uppercase;
            font-size: 0.74rem;
            letter-spacing: 0.14rem;
        }

        .chip.offline {
            border-color: rgba(127, 135, 151, 0.24);
            background: rgba(127, 135, 151, 0.08);
            color: var(--offline);
        }

        .back-link {
            display: inline-flex;
            align-items: center;
            justify-content: center;
            gap: 10px;
            min-height: 48px;
            padding: 0 18px;
            border-radius: 999px;
            border: 1px solid rgba(65, 245, 222, 0.26);
            color: var(--text);
            text-decoration: none;
            background: rgba(65, 245, 222, 0.08);
            box-shadow: 0 0 16px rgba(65, 245, 222, 0.12);
            transition: transform 0.18s ease, box-shadow 0.18s ease, border-color 0.18s ease;
        }

        .back-link:hover {
            transform: translateY(-1px);
            border-color: rgba(255, 79, 216, 0.32);
            box-shadow: 0 0 18px rgba(255, 79, 216, 0.16);
        }

        .device-panel {
            margin-top: 18px;
            padding: 22px;
            border-radius: calc(var(--radius) + 2px);
            background: linear-gradient(180deg, rgba(10, 16, 30, 0.96), rgba(7, 12, 24, 0.94));
            border: 1px solid rgba(65, 245, 222, 0.15);
            box-shadow: inset 0 0 0 1px rgba(255, 255, 255, 0.02), 0 18px 34px rgba(0, 0, 0, 0.34);
        }

        .device-panel.is-offline {
            border-color: rgba(127, 135, 151, 0.2);
            background: linear-gradient(180deg, rgba(18, 20, 28, 0.95), rgba(12, 14, 20, 0.95));
            color: var(--offline);
        }

        .device-panel.is-offline .status-line,
        .device-panel.is-offline .panel-copy,
        .device-panel.is-offline .status-row,
        .device-panel.is-offline .thread-name,
        .device-panel.is-offline .thread-text,
        .device-panel.is-offline .detail-heading,
        .device-panel.is-offline .device-name,
        .device-panel.is-offline .chip,
        .device-panel.is-offline .media-card-caption {
            color: var(--offline);
            text-shadow: none;
        }

        .device-panel.is-offline .chip {
            border-color: rgba(127, 135, 151, 0.22);
            background: rgba(127, 135, 151, 0.08);
            box-shadow: none;
        }

        .device-panel.is-offline .status-row {
            border-color: rgba(127, 135, 151, 0.16);
            background: rgba(127, 135, 151, 0.05);
        }

        .device-panel.is-offline img {
            filter: grayscale(1) saturate(0.2) brightness(0.75);
            opacity: 0.5;
        }

        .panel-copy {
            color: var(--muted);
            margin: 16px auto 0;
            width: min(720px, 100%);
            line-height: 1.6;
        }

        .status-line {
            margin: 18px 0 0;
            font-size: 1rem;
            text-shadow: 0 0 18px rgba(65, 245, 222, 0.12);
        }

        .status-line.online {
            color: var(--lime);
        }

        .status-line.offline {
            color: var(--red);
        }

        .status-list {
            display: grid;
            gap: 12px;
            margin-top: 24px;
        }

        .status-row {
            display: flex;
            align-items: center;
            justify-content: space-between;
            gap: 14px;
            padding: 14px 16px;
            text-align: left;
            border-radius: 16px;
            background: rgba(6, 10, 20, 0.56);
            border: 1px solid rgba(65, 245, 222, 0.1);
        }

        .thread-name {
            font-weight: 700;
            text-transform: uppercase;
            letter-spacing: 0.08em;
            color: var(--muted);
        }

        .thread-text {
            text-align: right;
            word-break: break-word;
        }

        .green { color: var(--lime); }
        .red { color: var(--red); }
        .yellow { color: var(--amber); }
        .gray,
        .grey { color: var(--offline); }
        .orange { color: #ffb86b; }
        .blue { color: #7bc6ff; }

        .image-grid {
            margin-top: 24px;
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
            gap: 16px;
        }

        .media-card {
            padding: 14px;
            border-radius: 18px;
            background: rgba(6, 10, 20, 0.62);
            border: 1px solid rgba(65, 245, 222, 0.1);
            box-shadow: inset 0 0 0 1px rgba(255, 255, 255, 0.02);
        }

        .media-card img {
            display: block;
            width: 100%;
            height: auto;
            border-radius: 12px;
            border: 1px solid rgba(255, 255, 255, 0.06);
        }

        .media-card-caption {
            margin-top: 10px;
            color: var(--muted);
            font-size: 0.88rem;
        }

        .empty-state {
            padding: 36px 18px;
            border-radius: var(--radius);
            background: rgba(7, 11, 21, 0.72);
            border: 1px dashed rgba(65, 245, 222, 0.24);
            color: var(--muted);
        }

        @media (max-width: 640px) {
            body {
                padding: 18px 12px 28px;
            }

            .shell {
                padding: 20px 14px 24px;
            }

            .device-panel {
                padding: 18px 14px;
            }

            .status-row {
                flex-direction: column;
                align-items: flex-start;
            }

            .thread-text {
                text-align: left;
            }
        }
    </style>
</head>
<body>
    <main class="shell">
        <header class="hero">
            <img src="titleimage.png" alt="R.U.M. Logger title image">
            <p class="eyebrow">Data recording backend for online devices of the</p>
            <h1>Raw Unified Multistream Logger</h1>
            <p class="subtitle">Online connected devices with correctly set %RUM_BACKEND% (to this domain) environment variable will report status here.</p>
            <p id="countdown"></p>
        </header>

        <div class="divider"></div>

        <script>
            let countdown = 5;
            const countdownElement = document.getElementById('countdown');

            function renderCountdown() {
                countdownElement.innerText = `Refreshing in ${countdown} seconds...`;
            }

            renderCountdown();

            const interval = setInterval(() => {
                countdown -= 1;
                renderCountdown();
                if (countdown === 0) {
                    clearInterval(interval);
                    location.reload();
                }
            }, 1000);
        </script>

        <?php if ($requestedDevice === null): ?>
            <?php if (count($deviceList) === 0): ?>
                <section class="empty-state">
                    <p>No devices found.</p>
                </section>
            <?php else: ?>
                <ul class="device-list">
                    <?php foreach ($deviceList as $deviceMeta): ?>
                        <li>
                            <a class="device-card<?php echo $deviceMeta['isOnline'] ? '' : ' is-offline'; ?>" href="?device=<?php echo escape_html($deviceMeta['device']); ?>">
                                <div class="device-name-row">
                                    <span class="device-name"><?php echo escape_html($deviceMeta['device']); ?></span>
                                    <?php if ($deviceMeta['isOnline']): ?>
                                        <span class="status-dot is-online" aria-hidden="true"></span>
                                    <?php endif; ?>
                                    <span class="chip<?php echo $deviceMeta['isOnline'] ? '' : ' offline'; ?>"><?php echo $deviceMeta['isOnline'] ? 'Online' : 'Offline'; ?></span>
                                </div>
                                <div class="device-meta">
                                    <span>Last upload: <?php echo escape_html(date('d.m.Y H:i:s', $deviceMeta['lastModified'])); ?></span>
                                    <span>Delta: <?php echo escape_html($deviceMeta['timeDelta']); ?></span>
                                </div>
                            </a>
                        </li>
                    <?php endforeach; ?>
                </ul>
            <?php endif; ?>
        <?php else: ?>
            <?php
            $deviceFile = get_device_file_name($requestedDevice);
            ?>
            <p><a class="back-link" href="index.php">Back to device overview</a></p>
            <?php if (file_exists($deviceFile) && is_file($deviceFile)): ?>
                <?php
                $deviceMeta = get_device_meta($deviceFile, $onlineThresholdSeconds);
                $deviceData = json_decode((string) file_get_contents($deviceFile), true);
                $imageFiles = array();

                for ($index = 0; $index <= 2; $index++) {
                    $imageFile = $requestedDevice . '_' . $index . '.png';
                    if (file_exists($imageFile) && (time() - filemtime($imageFile)) < 5 * 60) {
                        $imageFiles[] = $imageFile;
                    }
                }
                ?>
                <section class="device-panel<?php echo $deviceMeta['isOnline'] ? '' : ' is-offline'; ?>">
                    <div class="detail-heading">
                        <span class="device-name"><?php echo escape_html($requestedDevice); ?></span>
                        <?php if ($deviceMeta['isOnline']): ?>
                            <span class="status-dot is-online" aria-hidden="true"></span>
                        <?php endif; ?>
                        <span class="chip<?php echo $deviceMeta['isOnline'] ? '' : ' offline'; ?>"><?php echo $deviceMeta['isOnline'] ? 'Online' : 'Offline'; ?></span>
                    </div>
                    <p class="status-line <?php echo $deviceMeta['isOnline'] ? 'online' : 'offline'; ?>">
                        Last Update: <?php echo escape_html(date('d.m.Y H:i:s', $deviceMeta['lastModified'])); ?>
                        (Delta: <?php echo escape_html($deviceMeta['timeDelta']); ?>)
                    </p>
                    <?php if (!$deviceMeta['isOnline']): ?>
                        <p class="panel-copy">This device is currently offline. Status text and preview images are intentionally dimmed so stale data is visually distinct from live telemetry.</p>
                    <?php endif; ?>

                    <?php if (is_array($deviceData) && count($deviceData) > 0): ?>
                        <ul class="status-list">
                            <?php foreach ($deviceData as $thread => $status): ?>
                                <li class="status-row">
                                    <span class="thread-name"><?php echo escape_html($thread); ?></span>
                                    <span class="thread-text <?php echo escape_html(isset($status['color']) ? $status['color'] : 'gray'); ?>">
                                        <?php echo escape_html(isset($status['text']) ? $status['text'] : 'Unknown'); ?>
                                    </span>
                                </li>
                            <?php endforeach; ?>
                        </ul>
                    <?php else: ?>
                        <p class="panel-copy">Invalid JSON data in <?php echo escape_html($deviceFile); ?>.</p>
                    <?php endif; ?>

                    <?php if (count($imageFiles) > 0): ?>
                        <ul class="image-grid">
                            <?php foreach ($imageFiles as $imageFile): ?>
                                <li class="media-card">
                                    <img src="<?php echo escape_html($imageFile); ?>" alt="Preview <?php echo escape_html(pathinfo($imageFile, PATHINFO_FILENAME)); ?>">
                                    <div class="media-card-caption"><?php echo escape_html(pathinfo($imageFile, PATHINFO_BASENAME)); ?></div>
                                </li>
                            <?php endforeach; ?>
                        </ul>
                    <?php endif; ?>
                </section>
            <?php else: ?>
                <section class="empty-state">
                    <p>Device file not found or invalid.</p>
                </section>
            <?php endif; ?>
        <?php endif; ?>
    </main>
</body>
</html>