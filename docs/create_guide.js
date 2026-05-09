/**
 * Generates three user guide DOCX files:
 *   Sky_East_User_Guide.docx      — bilingual EN + 中文
 *   Sky_East_User_Guide_EN.docx   — English only
 *   Sky_East_User_Guide_ZH.docx   — Chinese only
 */
const DOCX_PATH = 'C:/Users/Administrator/AppData/Roaming/npm/node_modules/docx';
const {
  Document, Packer, Paragraph, TextRun, ImageRun, Table, TableRow, TableCell,
  Header, Footer, AlignmentType, HeadingLevel, BorderStyle, WidthType,
  ShadingType, PageNumber, PageBreak, LevelFormat
} = require(DOCX_PATH);

const fs   = require('fs');
const path = require('path');

const SCREENSHOTS = path.join(__dirname, 'screenshots');
const BASE_OUT    = 'C:/Users/Administrator/Desktop/Tool/PO_Automation_GIII/docs/';

// ── Page geometry (A4, 0.75" margins) ────────────────────────────────────────
const MARGIN    = 1080;
const PAGE_W    = 11906;
const CONTENT_W = PAGE_W - MARGIN * 2;  // 9746 DXA

// Screenshots captured at 1440 × 900 px (headless Chrome)
const IMG_PX_W = 630;
const IMG_PX_H = Math.round(IMG_PX_W * 900 / 1440);  // 394

// ── Colours ───────────────────────────────────────────────────────────────────
const BLUE  = '2C5F8A';
const BLACK = '1A1A1A';
const GREY  = '555555';
const LGREY = '888888';

// ── Helpers ───────────────────────────────────────────────────────────────────
const thin = c => ({ style: BorderStyle.SINGLE, size: 1, color: c });

function imgPara(filename, alt) {
  const data = fs.readFileSync(path.join(SCREENSHOTS, filename));
  return new Paragraph({
    alignment: AlignmentType.CENTER,
    spacing: { before: 120, after: 60 },
    border: { top: thin('DDDDDD'), bottom: thin('DDDDDD'), left: thin('DDDDDD'), right: thin('DDDDDD') },
    children: [new ImageRun({
      type: 'jpg', data,
      transformation: { width: IMG_PX_W, height: IMG_PX_H },
      altText: { title: alt, description: alt, name: alt }
    })]
  });
}

// Convert run descriptor array or plain string → TextRun[]
// Each element can be: string | { text, bold?, color? }
function mkRuns(src, defaultColor) {
  if (typeof src === 'string') {
    return [new TextRun({ text: src, size: 22, font: 'Arial', color: defaultColor })];
  }
  return src.map(r => {
    if (r instanceof TextRun) return r;
    if (typeof r === 'string') return new TextRun({ text: r, size: 22, font: 'Arial', color: defaultColor });
    return new TextRun({ size: 22, font: 'Arial', color: defaultColor, ...r });
  });
}

// Dedicated line-break run (avoids spreading TextRun class instances)
const brRun = () => new TextRun({ text: '', break: 1, size: 22, font: 'Arial' });

// Bold / Normal descriptor shorthand
const B = (text, color) => ({ text, bold: true,  color: color || BLACK });
const N = (text, color) => ({ text, bold: false, color: color || BLACK });

function sp()  { return new Paragraph({ spacing: { before: 60, after: 60 },   children: [] }); }
function hr()  { return new Paragraph({ spacing: { before: 160, after: 160 },
  border: { bottom: { style: BorderStyle.SINGLE, size: 4, color: 'CCCCCC' } }, children: [] }); }
function pb()  { return new Paragraph({ children: [new PageBreak()] }); }

// ── Mode-aware builder ────────────────────────────────────────────────────────
function buildDoc(mode) {
  // mode: 'bi' | 'en' | 'zh'
  const isBI = mode === 'bi';
  const isZH = mode === 'zh';

  // Heading helpers — return array of Paragraph objects
  function h1(en, zh) {
    const text = isZH ? zh : en;
    const rows = [new Paragraph({
      heading: HeadingLevel.HEADING_1,
      spacing: { before: 400, after: isBI ? 0 : 120 },
      children: [new TextRun({ text, bold: true, size: 32, font: 'Arial', color: BLUE })]
    })];
    if (isBI) rows.push(new Paragraph({
      spacing: { before: 0, after: 120 },
      children: [new TextRun({ text: zh, bold: true, size: 28, font: 'Arial', color: BLUE })]
    }));
    return rows;
  }

  function h2(en, zh) {
    const text = isZH ? zh : en;
    const rows = [new Paragraph({
      heading: HeadingLevel.HEADING_2,
      spacing: { before: 280, after: isBI ? 0 : 80 },
      children: [new TextRun({ text, bold: true, size: 26, font: 'Arial', color: BLUE })]
    })];
    if (isBI) rows.push(new Paragraph({
      spacing: { before: 0, after: 80 },
      children: [new TextRun({ text: zh, bold: true, size: 24, font: 'Arial', color: BLUE })]
    }));
    return rows;
  }

  function h3(en, zh) {
    const text = isZH ? zh : en;
    const rows = [new Paragraph({
      heading: HeadingLevel.HEADING_3,
      spacing: { before: 200, after: isBI ? 0 : 60 },
      children: [new TextRun({ text, bold: true, size: 24, font: 'Arial', color: BLACK })]
    })];
    if (isBI) rows.push(new Paragraph({
      spacing: { before: 0, after: 60 },
      children: [new TextRun({ text: zh, bold: true, size: 22, font: 'Arial', color: BLACK })]
    }));
    return rows;
  }

  // Body paragraph
  function p(enContent, zhContent, align) {
    const enRuns = mkRuns(enContent, BLACK);
    const zhRuns = mkRuns(zhContent, GREY);
    const children = isBI
      ? [...enRuns, brRun(), ...zhRuns]
      : isZH ? zhRuns : enRuns;
    return new Paragraph({ alignment: align || AlignmentType.LEFT,
      spacing: { before: 80, after: 80 }, children });
  }

  // Bullet
  function bullet(enContent, zhContent) {
    const enRuns = mkRuns(enContent, BLACK);
    const zhRuns = mkRuns(zhContent, GREY);
    const children = isBI
      ? [...enRuns, brRun(), ...zhRuns]
      : isZH ? zhRuns : enRuns;
    return new Paragraph({ numbering: { reference: 'bullets', level: 0 },
      spacing: { before: 60, after: 60 }, children });
  }

  // Numbered step
  function step(enContent, zhContent) {
    const enRuns = mkRuns(enContent, BLACK);
    const zhRuns = mkRuns(zhContent, GREY);
    const children = isBI
      ? [...enRuns, brRun(), ...zhRuns]
      : isZH ? zhRuns : enRuns;
    return new Paragraph({ numbering: { reference: 'steps', level: 0 },
      spacing: { before: 60, after: 60 }, children });
  }

  // Caption
  function cap(en, zh) {
    const text = isBI ? `${en}  /  ${zh}` : isZH ? zh : en;
    return new Paragraph({ alignment: AlignmentType.CENTER,
      spacing: { before: 60, after: 220 },
      children: [new TextRun({ text, italics: true, size: 20, font: 'Arial', color: LGREY })] });
  }

  // Info/note box
  function box(enText, zhText) {
    const bdr = thin('5B9BD5');
    const leftBdr = { style: BorderStyle.THICK, size: 8, color: BLUE };
    const noteLabel   = isZH ? '注意：' : 'Note: ';
    const noteContent = isZH ? zhText    : enText;
    const childrenArr = isBI
      ? [
          new TextRun({ text: 'Note: ', bold: true, size: 22, font: 'Arial', color: BLUE }),
          new TextRun({ text: enText, size: 22, font: 'Arial' }),
          new TextRun({ text: '注意：', bold: true, size: 22, font: 'Arial', color: BLUE, break: 1 }),
          new TextRun({ text: zhText, size: 22, font: 'Arial', color: GREY })
        ]
      : [
          new TextRun({ text: noteLabel, bold: true, size: 22, font: 'Arial', color: BLUE }),
          new TextRun({ text: noteContent, size: 22, font: 'Arial' })
        ];
    return new Table({
      width: { size: CONTENT_W, type: WidthType.DXA }, columnWidths: [CONTENT_W],
      rows: [new TableRow({ children: [new TableCell({
        borders: { top: bdr, bottom: bdr, left: leftBdr, right: bdr },
        shading: { fill: 'EEF4FB', type: ShadingType.CLEAR },
        margins: { top: 120, bottom: 120, left: 200, right: 200 },
        width: { size: CONTENT_W, type: WidthType.DXA },
        children: [new Paragraph({ spacing: { before: 0, after: 0 }, children: childrenArr })]
      })]})],
    });
  }

  // ── Header label ──────────────────────────────────────────────────────────
  const headerText = isBI ? 'PO Extractor  —  Sky East User Guide  /  Sky East 用户指南'
                   : isZH ? 'PO Extractor  —  Sky East 用户指南'
                   :        'PO Extractor  —  Sky East User Guide';

  // ── Title page ────────────────────────────────────────────────────────────
  const titleMain = isZH ? 'Sky East 用户指南' : 'Sky East User Guide';
  const titleSub  = isZH ? '适用于 Sky East 采购合同用户' : 'For Sky East Purchase Contract Users';
  const noteText  = isZH
    ? '本指南适用于具有标准（非管理员）账户的 Sky East 用户。'
    : 'This guide is for Sky East users with a standard (non-admin) account.';
  const noteLbl   = isZH ? '注意：' : 'Note:';

  const titleChildren = [
    sp(), sp(), sp(),
    new Paragraph({ alignment: AlignmentType.CENTER, spacing: { before: 480, after: 80 },
      children: [new TextRun({ text: 'PO Extractor', size: 64, bold: true, font: 'Arial', color: BLUE })] }),
    new Paragraph({ alignment: AlignmentType.CENTER, spacing: { before: 0, after: isBI ? 60 : 160 },
      children: [new TextRun({ text: isZH ? 'Sky East 用户指南' : 'Sky East User Guide', size: 44, font: 'Arial', color: '444444' })] }),
    ...(isBI ? [new Paragraph({ alignment: AlignmentType.CENTER, spacing: { before: 0, after: 80 },
      children: [new TextRun({ text: 'Sky East 用户指南', size: 36, font: 'Arial', color: '666666' })] })] : []),
    new Paragraph({ alignment: AlignmentType.CENTER, spacing: { before: isBI ? 80 : 0, after: 400 },
      children: [new TextRun({ text: titleSub + (isBI ? '  /  适用于 Sky East 采购合同用户' : ''),
        size: 22, italics: true, font: 'Arial', color: LGREY })] }),
    // info box on title page
    new Table({
      width: { size: 7000, type: WidthType.DXA }, columnWidths: [7000],
      rows: [new TableRow({ children: [new TableCell({
        borders: { top: thin('5B9BD5'), bottom: thin('5B9BD5'),
          left: { style: BorderStyle.THICK, size: 8, color: BLUE }, right: thin('5B9BD5') },
        shading: { fill: 'EEF4FB', type: ShadingType.CLEAR },
        margins: { top: 140, bottom: 140, left: 220, right: 220 },
        width: { size: 7000, type: WidthType.DXA },
        children: isBI
          ? [
              new Paragraph({ alignment: AlignmentType.CENTER, spacing: { before: 0, after: 40 },
                children: [new TextRun({ text: 'This guide is for Sky East users with a standard (non-admin) account.', size: 22, font: 'Arial', italics: true })] }),
              new Paragraph({ alignment: AlignmentType.CENTER, spacing: { before: 0, after: 0 },
                children: [new TextRun({ text: '本指南适用于具有标准（非管理员）账户的 Sky East 用户。', size: 22, font: 'Arial', italics: true, color: GREY })] })
            ]
          : [new Paragraph({ alignment: AlignmentType.CENTER, spacing: { before: 0, after: 0 },
              children: [new TextRun({ text: noteText, size: 22, font: 'Arial', italics: true })] })]
      })]})],
    }),
    new Paragraph({ alignment: AlignmentType.CENTER, spacing: { before: 0, after: 0 }, children: [] }),
    pb()
  ];

  // ── Document body ─────────────────────────────────────────────────────────
  const body = [
    ...titleChildren,

    // ── SECTION 1 ─────────────────────────────────────────────────────────
    ...h1('1.  Getting Started — Logging In', '1.  入门 — 登录'),
    p('Open your browser and navigate to the PO Extractor URL provided by your administrator. You will see the login screen below.',
      '打开浏览器，访问管理员提供的 PO Extractor 网址。您将看到如下登录界面。'),
    sp(),
    imgPara('sc_01_login.jpg', 'Login screen'),
    cap('Figure 1 – Login screen', '图 1 – 登录界面'),

    ...h3('Steps to log in:', '登录步骤：'),
    step([B('Username: '), N('Enter your username in the Username field.')],
         [B('用户名：', GREY), N('在用户名输入框中输入您的用户名。', GREY)]),
    step([B('Password: '), N('Enter your password in the Password field.')],
         [B('密码：', GREY), N('在密码输入框中输入您的密码。', GREY)]),
    step([B('Sign In: '), N('Click the '), B('Sign In'), N(' button.')],
         [B('登录：', GREY), N('点击"', GREY), B('登录', GREY), N('"按钮。', GREY)]),
    sp(),
    p(['After a successful login you will land on the main dashboard. Click the ', B('Sky East'), ' tab in the top navigation bar to begin working with purchase contracts.'],
      ['登录成功后，您将进入主仪表板。点击顶部导航栏中的 ', B('Sky East', GREY), ' 标签页，开始处理采购合同。']),
    sp(),
    imgPara('sc_02_main_dashboard.jpg', 'Main dashboard'),
    cap('Figure 2 – Main dashboard after login (Sky East tab is in the top navigation bar)',
        '图 2 – 登录后的主仪表板（顶部导航栏中的 Sky East 标签页）'),
    pb(),

    // ── SECTION 2 ─────────────────────────────────────────────────────────
    ...h1('2.  Sky East Purchase Contracts', '2.  Sky East 采购合同'),
    p(['The ', B('Sky East'), ' tab is your main workspace. It contains three sub-tabs: ', B('New Contracts'), ', ', B('Contract History'), ', and ', B('Missing Fields'), '.'],
      ['Sky East 标签页是您的主要工作区，包含三个子标签页：', B('新建合同', GREY), '、', B('合同历史', GREY), ' 和 ', B('缺失字段', GREY), '。']),
    sp(),
    imgPara('sc_03_skyeast_new_contracts.jpg', 'Sky East New Contracts'),
    cap('Figure 3 – Sky East tab — New Contracts', '图 3 – Sky East 标签页 — 新建合同'),

    ...h2('2.1  Uploading a New Contract', '2.1  上传新合同'),
    p(['The ', B('New Contracts'), ' sub-tab is where you upload Sky East purchase contract Excel files for processing.'],
      ['在"', B('新建合同', GREY), '"子标签页中，您可以上传 Sky East 采购合同 Excel 文件进行处理。']),
    sp(),

    ...h3('Step 1 — Upload Order Files', '第一步 — 上传订单文件'),
    p(['Under ', B('Order Files (Sky East Purchase Contract xlsx)'), ', click the ', B('Upload'), ' button and select one or more Sky East purchase contract Excel files (XLSX, XLS, or XLSM format, up to 200 MB per file).'],
      ['在"', B('订单文件（Sky East 采购合同 xlsx）', GREY), '"区域，点击"', B('上传', GREY), '"按钮，选择一个或多个 Sky East 采购合同 Excel 文件（XLSX、XLS 或 XLSM 格式，每个文件最大 200 MB）。']),
    sp(),
    box('Files with the same PC No. are automatically merged — quantities are added together. If size breakdowns have changed, the system detects it as an amendment and logs it to Contract History.',
        '相同 PC 编号的文件会自动合并——数量相加。若尺码分配有所变化，系统将识别为修改并记录至合同历史。'),
    sp(),

    ...h3('Step 2 — Reference Files (Optional)', '第二步 — 参考文件（可选）'),
    p(['The ', B('Reference files'), ' section is optional but recommended. Click the arrow to expand it.'],
      ['参考文件部分为可选，但建议上传。点击箭头展开该区域。']),
    sp(),
    imgPara('sc_04_skyeast_ref_files.jpg', 'Reference files expanded'),
    cap('Figure 4 – Reference files section expanded', '图 4 – 参考文件区域已展开'),
    sp(),
    bullet([B('Config SKU file (Zalando PO report xlsx): '), N('Upload the Zalando PO report to cross-reference style and SKU data.')],
           [B('Config SKU 文件（Zalando PO 报表 xlsx）：', GREY), N('上传 Zalando PO 报表，用于款式和 SKU 数据交叉核对。', GREY)]),
    bullet([B('HHN contract No. file: '), N('Upload the HHN 大货进度表 (Progress Tracker) Excel file to enable automatic Chinese color mapping.')],
           [B('HHN 合同编号文件：', GREY), N('上传 HHN 大货进度表 Excel 文件，以启用自动中文颜色映射。', GREY)]),
    sp(),

    ...h3('Step 3 — Chinese Color Mapping Source (中文颜色 / 中文颜色代码)', '第三步 — 中文颜色映射来源'),
    p('Below the reference files, choose how the system should look up Chinese color names:',
      '在参考文件下方，选择系统查找中文颜色名称的方式：'),
    bullet([B('Internal Database'), N(' — Use the built-in color translation table maintained in the Colors tab.')],
           [B('内部数据库', GREY), N(' — 使用颜色标签页中维护的内置颜色翻译表。', GREY)]),
    bullet([B('大货进度表 (HHN Contract File)'), N(' — Look up Chinese color names directly from the HHN Progress Tracker file uploaded in Step 2. Recommended when the progress tracker is available.')],
           [B('大货进度表（HHN 合同文件）', GREY), N(' — 直接从第二步上传的 HHN 大货进度表中查找中文颜色名称。有进度表时推荐使用此选项。', GREY)]),
    sp(),

    ...h3('Step 4 — Process and Download', '第四步 — 处理与下载'),
    p(['Once files are uploaded and settings are configured, click the ', B('Process'), ' button (scroll down to find it). The system will process the contracts and generate:'],
      ['文件上传并完成设置后，点击"', B('处理', GREY), '"按钮（向下滚动可找到）。系统将处理合同并生成以下文件：']),
    bullet([B('Buy Plan workbook'), N(' — the main output Excel file')],
           [B('买手计划工作簿', GREY), N(' — 主要输出 Excel 文件', GREY)]),
    bullet([B('核料 (Nukuryou) workbook'), N(' — fabric requisition summary')],
           [B('核料工作簿', GREY), N(' — 面料申请摘要', GREY)]),
    sp(),
    p('Download buttons will appear after processing is complete. Click each button to save the files to your computer.',
      '处理完成后将显示下载按钮。点击各按钮将文件保存至您的电脑。'),
    pb(),

    // ── 2.2 ──────────────────────────────────────────────────────────────
    ...h2('2.2  Contract History', '2.2  合同历史'),
    p(['Click the ', B('Contract History'), ' sub-tab to view all previously saved contracts.'],
      ['点击"', B('合同历史', GREY), '"子标签页，查看所有已保存的合同。']),
    sp(),
    imgPara('sc_06_contract_history.jpg', 'Contract History'),
    cap('Figure 5 – Contract History showing saved PC numbers', '图 5 – 合同历史：显示已保存的 PC 编号'),
    sp(),
    p('The table displays all saved contracts with columns: PC No., PC Date, Buyer, Seller, Styles, Total Qty, Currency, Trade Terms.',
      '表格显示所有已保存合同，包含：PC 编号、PC 日期、买方、卖方、款数、总数量、货币和贸易条款。'),
    sp(),
    ...h3('Downloading by PC No.', '按 PC 编号下载'),
    p(['Scroll down to the ', B('Download items by PC No.'), ' section. Select one or more PC numbers from the list and click the download button to regenerate and download the Buy Plan workbook for those specific contracts.'],
      ['向下滚动至"', B('按 PC 编号下载条目', GREY), '"区域。从列表中选择一个或多个 PC 编号，点击下载按钮，即可重新生成并下载对应合同的买手计划工作簿。']),
    sp(), hr(), sp(),

    // ── 2.3 ──────────────────────────────────────────────────────────────
    ...h2('2.3  Missing Fields', '2.3  缺失字段'),
    p(['Click the ', B('Missing Fields'), ' sub-tab to view and fix items that have incomplete data (e.g., missing Fabric No. or HHN Contract No.).'],
      ['点击"', B('缺失字段', GREY), '"子标签页，查看并修正数据不完整的条目（如缺少面料编号或 HHN 合同编号）。']),
    sp(),
    imgPara('sc_07_missing_fields.jpg', 'Missing Fields'),
    cap('Figure 6 – Missing Fields tab showing items with incomplete data', '图 6 – 缺失字段标签页：显示数据不完整的条目'),
    sp(),
    step(['Use the ', B('Filter by PC No.'), ' dropdown to narrow down the list to a specific purchase contract.'],
         ['使用"', B('按 PC 编号筛选', GREY), '"下拉菜单，将列表缩小至特定采购合同。']),
    step('Click directly on a cell in the table to edit it inline.',
         '直接点击表格中的单元格进行行内编辑。'),
    step(['After making your corrections, click ', B('Save Changes'), ' to update the database.'],
         ['更正完成后，点击"', B('保存更改', GREY), '"更新数据库。']),
    pb(),

    // ── SECTION 3 ─────────────────────────────────────────────────────────
    ...h1('3.  Order Summary', '3.  订单摘要'),
    p(['Click the ', B('Summary'), ' tab in the top navigation bar to see an aggregated overview of all your orders.'],
      ['点击顶部导航栏中的"', B('摘要', GREY), '"标签页，查看所有订单的汇总概览。']),
    sp(),
    imgPara('sc_09_summary.jpg', 'Order Summary'),
    cap('Figure 7 – Order Summary showing total POs, styles, and units', '图 7 – 订单摘要：显示总 PO 数、款数和数量'),
    sp(),
    p('The summary shows:', '摘要显示：'),
    bullet([B('Companies'), N(' — number of companies you have access to')],
           [B('公司', GREY), N(' — 您有权访问的公司数量', GREY)]),
    bullet([B('Total POs'), N(' — total number of purchase orders')],
           [B('总 PO 数', GREY), N(' — 采购订单总数', GREY)]),
    bullet([B('Total Styles'), N(' — total style count across all orders')],
           [B('总款数', GREY), N(' — 所有订单的款式总数', GREY)]),
    bullet([B('Total Units'), N(' — total quantity across all orders')],
           [B('总数量', GREY), N(' — 所有订单的总数量', GREY)]),
    sp(),
    p(['The table below breaks down the totals by company. Expand ', B('Sky East — full item list'), ' to browse all individual items, and click ', B('Download Full Summary'), ' to export the data to Excel.'],
      ['下方表格按公司分类汇总。展开"', B('Sky East — 完整条目列表', GREY), '"可浏览所有单独条目，点击"', B('下载完整摘要', GREY), '"可将数据导出至 Excel。']),
    sp(), hr(), sp(),

    // ── SECTION 4 ─────────────────────────────────────────────────────────
    ...h1('4.  Colors Reference Table', '4.  颜色参考表'),
    p(['Click the ', B('Colors'), ' tab in the top navigation bar to view the English-to-Chinese color name mapping table.'],
      ['点击顶部导航栏中的"', B('颜色', GREY), '"标签页，查看英文到中文的颜色名称映射表。']),
    sp(),
    imgPara('sc_08_colors.jpg', 'Color Name Translation'),
    cap('Figure 8 – Color Name Translation table', '图 8 – 颜色名称翻译表'),
    sp(),
    p(['This table maps English color names to their Chinese equivalents (中文颜色) by client and brand. It is used by the system when ', B('Internal Database'), ' is selected as the color mapping source.'],
      ['该表格按客户和品牌，将英文颜色名称映射至对应的中文颜色名称。当颜色映射来源选择"', B('内部数据库', GREY), '"时，系统将使用此表格。']),
    sp(),
    box('As a standard user, you can view the color table. If you notice a missing or incorrect color mapping, contact your administrator to have it updated.',
        '作为标准用户，您可以查看颜色表格。如发现颜色映射缺失或有误，请联系管理员进行更新。'),
    pb(),

    // ── SECTION 5 ─────────────────────────────────────────────────────────
    ...h1('5.  Account Management', '5.  账户管理'),
    ...h2('5.1  Changing Your Password', '5.1  修改密码'),
    p(['In the left sidebar, click ', B('Change Password'), ' (click the arrow to expand it). Enter your current password, then enter and confirm your new password, and click ', B('Save'), '.'],
      ['在左侧边栏中，点击"', B('修改密码', GREY), '"（点击箭头展开）。输入当前密码，然后输入并确认新密码，点击"', B('保存', GREY), '"。']),
    sp(),
    ...h2('5.2  Signing Out', '5.2  退出登录'),
    p(['In the left sidebar, click the ', B('Sign Out'), ' button to log out of the application.'],
      ['在左侧边栏中，点击"', B('退出登录', GREY), '"按钮，退出应用程序。']),
    sp(), hr(), sp(),

    // ── TIPS ──────────────────────────────────────────────────────────────
    ...h1('Tips and Notes', '提示与注意事项'),
    bullet([B('File formats: '), N('Order files must be Excel format (XLSX, XLS, XLSM). PDF files are not supported for Sky East contracts.')],
           [B('文件格式：', GREY), N('订单文件必须为 Excel 格式（XLSX、XLS、XLSM）。Sky East 合同不支持 PDF 文件。', GREY)]),
    bullet([B('Same PC No. merging: '), N('If you upload two files with the same PC number, their quantities are combined. The system will flag any size breakdown changes as amendments.')],
           [B('相同 PC 编号合并：', GREY), N('若上传两个 PC 编号相同的文件，其数量将被合并。系统会将任何尺码分配变化标记为修改。', GREY)]),
    bullet([B('Language: '), N('The interface supports English and Chinese. Click the '), B('切换中文'), N(' button in the sidebar to switch to Chinese.')],
           [B('语言：', GREY), N('界面支持英文和中文。点击侧边栏中的"', GREY), B('切换中文', GREY), N('"按钮可切换至中文界面。', GREY)]),
    bullet([B('Contact your administrator'), N(' if you need access to additional companies or encounter any login issues.')],
           [B('请联系管理员', GREY), N('，如需访问其他公司或遇到登录问题。', GREY)]),
  ];

  return new Document({
    numbering: {
      config: [
        { reference: 'bullets', levels: [{ level: 0, format: LevelFormat.BULLET, text: '•',
            alignment: AlignmentType.LEFT, style: { paragraph: { indent: { left: 720, hanging: 360 } } } }] },
        { reference: 'steps',   levels: [{ level: 0, format: LevelFormat.DECIMAL, text: '%1.',
            alignment: AlignmentType.LEFT, style: { paragraph: { indent: { left: 720, hanging: 360 } } } }] }
      ]
    },
    styles: {
      default: { document: { run: { font: 'Arial', size: 22 } } },
      paragraphStyles: [
        { id: 'Heading1', name: 'Heading 1', basedOn: 'Normal', next: 'Normal', quickFormat: true,
          run: { size: 32, bold: true, font: 'Arial', color: BLUE },
          paragraph: { spacing: { before: 400, after: 0 }, outlineLevel: 0 } },
        { id: 'Heading2', name: 'Heading 2', basedOn: 'Normal', next: 'Normal', quickFormat: true,
          run: { size: 26, bold: true, font: 'Arial', color: BLUE },
          paragraph: { spacing: { before: 280, after: 0 }, outlineLevel: 1 } },
        { id: 'Heading3', name: 'Heading 3', basedOn: 'Normal', next: 'Normal', quickFormat: true,
          run: { size: 24, bold: true, font: 'Arial', color: BLACK },
          paragraph: { spacing: { before: 200, after: 0 }, outlineLevel: 2 } }
      ]
    },
    sections: [{
      properties: {
        page: {
          size: { width: PAGE_W, height: 16838 },
          margin: { top: MARGIN, right: MARGIN, bottom: MARGIN, left: MARGIN }
        }
      },
      headers: { default: new Header({ children: [new Paragraph({
        border: { bottom: { style: BorderStyle.SINGLE, size: 4, color: BLUE } },
        spacing: { before: 0, after: 120 },
        children: [new TextRun({ text: headerText, size: 18, font: 'Arial', color: LGREY })]
      })] }) },
      footers: { default: new Footer({ children: [new Paragraph({
        border: { top: { style: BorderStyle.SINGLE, size: 4, color: 'CCCCCC' } },
        spacing: { before: 120, after: 0 },
        alignment: AlignmentType.RIGHT,
        children: [
          new TextRun({ text: 'Page ', size: 18, font: 'Arial', color: LGREY }),
          new TextRun({ children: [PageNumber.CURRENT], size: 18, font: 'Arial', color: LGREY }),
          new TextRun({ text: ' of ', size: 18, font: 'Arial', color: LGREY }),
          new TextRun({ children: [PageNumber.TOTAL_PAGES], size: 18, font: 'Arial', color: LGREY })
        ]
      })] }) },
      children: body
    }]
  });
}

// ── Generate all three files ──────────────────────────────────────────────────
const targets = [
  { mode: 'bi', file: 'Sky_East_User_Guide.docx' },
  { mode: 'en', file: 'Sky_East_User_Guide_EN.docx' },
  { mode: 'zh', file: 'Sky_East_User_Guide_ZH.docx' },
];

Promise.all(
  targets.map(({ mode, file }) =>
    Packer.toBuffer(buildDoc(mode)).then(buf => {
      const out = BASE_OUT + file;
      fs.writeFileSync(out, buf);
      console.log(`Written: ${file}  (${Math.round(buf.length / 1024)} KB)`);
    })
  )
).catch(err => { console.error(err.message); process.exit(1); });
