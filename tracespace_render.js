const fs = require('fs');
const path = require('path');
const pcbStackup = require('pcb-stackup');

// Hàm đệ quy để quét sâu vào mọi thư mục con (Sub-directories)
function getAllFiles(dirPath, arrayOfFiles) {
    const files = fs.readdirSync(dirPath);
    arrayOfFiles = arrayOfFiles || [];
    files.forEach(function(file) {
        const fullPath = path.join(dirPath, file);
        if (fs.statSync(fullPath).isDirectory()) {
            arrayOfFiles = getAllFiles(fullPath, arrayOfFiles);
        } else {
            arrayOfFiles.push(fullPath);
        }
    });
    return arrayOfFiles;
}

function processGerbers(tempDir) {
    // Bổ sung thêm dải đuôi file của Allegro, Altium, OrCAD, PADS
    const validExts = [
        '.gbl', '.gtl', '.gbs', '.gts', '.gbo', '.gto', '.gko', 
        '.gm1', '.gm2', '.gm13', '.gm15', '.drl', '.xln', '.gbr', 
        '.art', '.cmp', '.sol', '.stc', '.sts', '.plc', '.pls', '.spt', '.spb'
    ];
    
    // Quét toàn bộ file trong thư mục giải nén (bao gồm cả thư mục con)
    const allFiles = getAllFiles(tempDir);
    
    // Lọc ra các file vector PCB hợp lệ
    const gerberFiles = allFiles.filter(f => {
        const ext = path.extname(f).toLowerCase();
        return validExts.includes(ext);
    });

    if (gerberFiles.length === 0) {
        console.log(JSON.stringify({ 
            status: "error", 
            message: "Không tìm thấy file vector Gerber/Drill hợp lệ trong bất kỳ thư mục con nào." 
        }));
        return;
    }

    const layers = gerberFiles.map(file => ({
        filename: path.basename(file), // pcb-stackup dựa vào tên file để nhận diện mặt Top/Bot
        gerber: fs.readFileSync(file)
    }));

    pcbStackup(layers).then(stackup => {
        const topSvgPath = path.join(tempDir, 'top_render.svg');
        const botSvgPath = path.join(tempDir, 'bottom_render.svg');

        if (stackup.top && stackup.top.svg) fs.writeFileSync(topSvgPath, stackup.top.svg);
        if (stackup.bottom && stackup.bottom.svg) fs.writeFileSync(botSvgPath, stackup.bottom.svg);

        console.log(JSON.stringify({
            status: "success",
            top_svg: stackup.top ? topSvgPath : null,
            bottom_svg: stackup.bottom ? botSvgPath : null
        }));
    }).catch(err => {
        console.log(JSON.stringify({ status: "error", message: err.message }));
    });
}

const targetDir = process.argv[2];
if (targetDir) {
    processGerbers(targetDir);
} else {
    console.log(JSON.stringify({ status: "error", message: "Chưa cung cấp đường dẫn thư mục tạm." }));
}