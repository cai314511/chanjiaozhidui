# 三端透明角色图集

来源为用户提供的 `Assets/agent/` 下三端主形象与九宫格。原始文件保留。使用内置 imagegen 编辑工具进行透明角色提取与统一排版，未使用 CLI 或额外 API 密钥。

三个图集分别为 `student.png`、`employer.png`、`university.png`，均为1983×793 RGBA PNG，具有真实透明通道。网页以5列2行等分显示：第0格是主形象，第1—9格对应九宫格阅读顺序。光环、服装、角色身份和手持道具按原素材保留；去除海报标题、卡片边框与场景背景。形象为原素材的生成式整理版本，不是原海报逐像素裁切。

## 编辑提示词

三次调用均以该角色的主形象作为图1、九宫格作为图2，设置 `transparent_background=true`。通用提示词：

> Use case: background-extraction / identity-preserve. Create a production transparent PNG sprite atlas from these TWO EDIT TARGET images. Image 1 is the main role mascot; image 2 contains nine different poses of SAME mascot. Preserve exactly the cute white robot identity, cyan luminous halo and face, original illustration style. Output ONE landscape atlas arranged in EXACTLY 5 equal-width columns and 2 equal-height rows (10 cells, row-major). Entire background genuinely transparent. Cell 0: main mascot from image 1, holding its original prop. Cells 1..9: the nine poses from image 2, in original reading order: greeting and all remaining original activities through resting/charging. EXTRACT CHARACTERS AND HELD PROPS ONLY; delete every original backdrop, border, text plaque, titles, scenic element, separate floating icon and text. Include original books/laptop/clipboard/trophy if actually held or supporting the character. Each figure centered in its own cell, with consistent head size and face at same vertical position; figure fits safely within central 85% of cell, no touching neighboring cells, halo and hands fully visible. Use lower torso/waist baseline consistent throughout, as a unified bust mascot set. No grid lines, no labels, no text, no checkerboard. Render ten crisp isolated character cutouts. Do not redesign characters, do not add extra figures. Atlas must be divisible in 5 by 2 equal cells.

分别增加身份约束：高校 `purple academic gown, mortarboard and round cyan glasses`；企业 `navy business suit, blue necktie and gold lapel badge`；学生 `blue baseball cap, white cyan hoodie and blue backpack`。

实际出场、漂浮和姿态过渡由 `web/role-mascots.js` 及 `web/role-mascots.css` 实现；不将九种独立姿态作为连续肢体动画帧直接跳切。
