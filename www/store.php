<?php
if ($_SERVER['REQUEST_METHOD'] == 'POST' && isset($_FILES['file'])) {
    $file = $_FILES['file'];
    $fileType = strtolower(pathinfo($file['name'], PATHINFO_EXTENSION));

    if ($fileType == 'json' || $fileType == 'png') {
        $targetDir = "./";
        $targetFile = $targetDir . basename($file['name']);

        if (move_uploaded_file($file['tmp_name'], $targetFile)) {
            echo "The file " . htmlspecialchars(basename($file['name'])) . " has been uploaded.";
        } else {
            echo "Sorry, there was an error uploading your file.";
        }
    } else {
        echo "Nope.";
    }
} else {
    echo "No file uploaded.";
}
?>