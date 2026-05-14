<?php

declare(strict_types=1);

require '/var/www/html/wp-load.php';

function ensure_post(string $slug, string $title, string $content): int
{
    $existing = get_page_by_path($slug, OBJECT, 'post');

    $postarr = [
        'post_title' => $title,
        'post_name' => $slug,
        'post_content' => $content,
        'post_status' => 'publish',
        'post_type' => 'post',
    ];

    if ($existing instanceof WP_Post) {
        $postarr['ID'] = $existing->ID;
    }

    $postId = wp_insert_post($postarr, true);
    if (is_wp_error($postId)) {
        throw new RuntimeException($postId->get_error_message());
    }

    return (int) $postId;
}

function build_large_text(int $targetBytes): string
{
    $paragraph = '<p>Lorem ipsum dolor sit amet, consectetur adipiscing elit. '
        . 'Suspendisse potenti. Praesent volutpat, velit at cursus vulputate, '
        . 'urna augue placerat velit, a tempor magna sapien eu justo. '
        . 'Vestibulum ante ipsum primis in faucibus orci luctus et ultrices '
        . 'posuere cubilia curae; Integer a ligula et lectus bibendum '
        . 'sollicitudin. Pellentesque habitant morbi tristique senectus et netus '
        . 'et malesuada fames ac turpis egestas.</p>';

    $content = '';
    while (strlen($content) < $targetBytes) {
        $content .= $paragraph;
    }

    return $content;
}

$uploadDir = wp_upload_dir();
$baseUrl = rtrim($uploadDir['url'], '/');

$img1mbUrl = $baseUrl . '/test-img-1mb.bmp';
$img300Url = $baseUrl . '/test-img-300kb.bmp';

$img1mbContent = '<p>Post de teste com imagem de aproximadamente 1 MB.</p>'
    . '<img src="' . esc_url($img1mbUrl) . '" alt="Imagem de teste 1MB" />';

$img300Content = '<p>Post de teste com imagem de aproximadamente 300 KB.</p>'
    . '<img src="' . esc_url($img300Url) . '" alt="Imagem de teste 300KB" />';

$text400Content = build_large_text(400 * 1024);

$postImg1mb = ensure_post('teste-img-1mb', 'Teste Imagem 1MB', $img1mbContent);
$postText400 = ensure_post('teste-texto-400kb', 'Teste Texto 400KB', $text400Content);
$postImg300 = ensure_post('teste-img-300kb', 'Teste Imagem 300KB', $img300Content);

echo 'POST_ID_IMG1MB=' . $postImg1mb . PHP_EOL;
echo 'POST_ID_TEXT400=' . $postText400 . PHP_EOL;
echo 'POST_ID_IMG300=' . $postImg300 . PHP_EOL;
