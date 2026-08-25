import os
import sys
import time
import shutil

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

def main():
    print("=" * 65)
    print("      DONG BO DU LIEU TU DAO VANG SANG QUANT DATA LAKE")
    print("=" * 65)
    
    gdrive_root = r"I:\My Drive"
    src_root = os.path.join(gdrive_root, "DaoVang_Data_Backup", "latest_data")
    dst_root = os.path.join(gdrive_root, "Quant_Data")
    
    if not os.path.exists(src_root):
        print(f"[LOI] Khong tim thay thu muc nguon: {src_root}")
        print("Vui long kiem tra Google Drive (o I:) da duoc mount chua.")
        return
        
    start_time = time.time()
    copied_count = 0
    skipped_count = 0
    error_count = 0
    
    # 1. Cap nhat Database live.duckdb
    print("\n[1/2] Dang kiem tra Database (live.duckdb)...")
    src_db = os.path.join(src_root, "live.duckdb")
    dst_db_dir = os.path.join(dst_root, "databases")
    os.makedirs(dst_db_dir, exist_ok=True)
    dst_db = os.path.join(dst_db_dir, "live.duckdb")
    
    if os.path.exists(src_db):
        try:
            src_mtime = os.path.getmtime(src_db)
            dst_mtime = os.path.getmtime(dst_db) if os.path.exists(dst_db) else 0
            if src_mtime > dst_mtime or not os.path.exists(dst_db):
                print(f"  -> Cap nhat live.duckdb moi nhat ({os.path.getsize(src_db)/(1024*1024):.1f} MB)...")
                shutil.copy2(src_db, dst_db)
                copied_count += 1
            else:
                print("  -> live.duckdb da o ban moi nhat (bo qua).")
                skipped_count += 1
        except Exception as e:
            print(f"  [Canh bao] Loi sao chep live.duckdb: {e}")
            error_count += 1

    # 2. Cap nhat cac file Parquet moi
    print("\n[2/2] Dang kiem tra va bo sung cac file Parquet moi...")
    src_norm = os.path.join(src_root, "normalized")
    dst_norm = os.path.join(dst_root, "normalized")
    
    if os.path.exists(src_norm):
        for root, dirs, files in os.walk(src_norm):
            rel_dir = os.path.relpath(root, src_norm)
            target_dir = os.path.join(dst_norm, rel_dir) if rel_dir != "." else dst_norm
            
            for f in files:
                if not f.endswith(".parquet"):
                    continue
                    
                src_file = os.path.join(root, f)
                dst_file = os.path.join(target_dir, f)
                
                needs_copy = False
                try:
                    if not os.path.exists(dst_file):
                        needs_copy = True
                    else:
                        if os.path.getsize(src_file) != os.path.getsize(dst_file):
                            needs_copy = True
                        elif os.path.getmtime(src_file) > os.path.getmtime(dst_file) + 2:
                            needs_copy = True
                except Exception:
                    needs_copy = True
                
                if needs_copy:
                    try:
                        os.makedirs(target_dir, exist_ok=True)
                        shutil.copy2(src_file, dst_file)
                        copied_count += 1
                        if copied_count <= 5 or copied_count % 50 == 0:
                            print(f"  + Da bo sung: {f}")
                    except Exception as e:
                        error_count += 1
                else:
                    skipped_count += 1

    elapsed = time.time() - start_time
    print("\n" + "=" * 65)
    print("                 KET QUA DONG BO")
    print("=" * 65)
    print(f"Thoi gian thuc hien : {elapsed:.2f} giay")
    print(f"File moi da bo sung   : {copied_count:,} files")
    print(f"File da san sang      : {skipped_count:,} files (giu nguyen)")
    if error_count > 0:
        print(f"So file gap su co    : {error_count} files")
    print("=" * 65)
    print("HOAN TAT! Quant_Data da duoc dong bo san sang su dung.")
    print("=" * 65)

if __name__ == "__main__":
    main()