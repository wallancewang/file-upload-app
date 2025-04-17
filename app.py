from fastapi import FastAPI, File, UploadFile, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
import zipfile
import os
import time
import uuid
import shutil
from typing import Dict

app = FastAPI()

# 允许跨域请求
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# 全局存储任务状态
tasks: Dict[str, Dict] = {}

def process_files(task_id: str, java_files: list, temp_dir: str):
    try:
        total = len(java_files)
        tasks[task_id].update({
            "total": total,
            "processed": 0,
            "results": {},
            "completed": False,
            "error": None
        })
        
        for idx, file_path in enumerate(java_files):
            try:
                # 统计行数
                with open(file_path, "r", encoding="utf-8") as f:
                    lines = len(f.readlines())
                
                # 记录结果
                rel_path = os.path.relpath(file_path, temp_dir)
                tasks[task_id]["results"][rel_path] = lines
                tasks[task_id]["processed"] = idx + 1
                time.sleep(1)  # 每个文件处理间隔1秒
            except Exception as e:
                tasks[task_id]["error"] = f"处理文件 {file_path} 失败: {str(e)}"
                break
        
        tasks[task_id]["completed"] = True
    except Exception as e:
        tasks[task_id]["error"] = str(e)
    finally:
        # 清理临时目录
        shutil.rmtree(temp_dir, ignore_errors=True)

@app.post("/upload")
async def upload_file(
    background_tasks: BackgroundTasks, 
    file: UploadFile = File(...)
):
    task_id = str(uuid.uuid4())
    temp_dir = os.path.join("temp", task_id)
    os.makedirs(temp_dir, exist_ok=True)

    # 保存ZIP文件
    zip_path = os.path.join(temp_dir, file.filename)
    async with open(zip_path, "wb") as f:
        content = await file.read()
        await f.write(content)
    
    # 解压文件
    try:
        with zipfile.ZipFile(zip_path, "r") as zip_ref:
            zip_ref.extractall(temp_dir)
    except zipfile.BadZipFile:
        return JSONResponse(
            status_code=400,
            content={"error": "无效的ZIP文件"}
        )
    
    # 查找所有Java文件
    java_files = []
    for root, _, files in os.walk(temp_dir):
        for file in files:
            if file.endswith(".java"):
                java_files.append(os.path.join(root, file))
    
    if not java_files:
        return JSONResponse(
            status_code=400,
            content={"error": "ZIP文件中没有Java文件"}
        )
    
    # 初始化任务状态
    tasks[task_id] = {
        "temp_dir": temp_dir,
        "error": None
    }
    
    # 添加后台任务
    background_tasks.add_task(process_files, task_id, java_files, temp_dir)
    
    return {"task_id": task_id}

@app.get("/progress/{task_id}")
def get_progress(task_id: str):
    task = tasks.get(task_id)
    if not task:
        return JSONResponse(
            status_code=404,
            content={"error": "任务不存在"}
        )
    
    return {
        "total": task.get("total", 0),
        "processed": task.get("processed", 0),
        "results": task.get("results", {}),
        "completed": task.get("completed", False),
        "error": task.get("error")
    }

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)