from fastapi import FastAPI, UploadFile, File, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
import os
import shutil
import json
from fontTools.ttLib import TTFont, sfnt
from fontTools.subset import Subsetter
import pathlib
import io

app = FastAPI()

# CORS middleware configuration
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Create data directory if it doesn't exist
DATA_DIR = pathlib.Path("data/fonts")
DATA_DIR.mkdir(parents=True, exist_ok=True)

# Mount the data directory for fonts
app.mount("/fonts", StaticFiles(directory="data/fonts"), name="fonts")

# Mount the static files for the frontend
app.mount("/assets", StaticFiles(directory="dist/assets"), name="static")

@app.get("/")
async def serve_spa():
    return FileResponse("dist/index.html")

@app.get("/api/fonts")
async def get_fonts():
    fonts = []
    for family_dir in sorted(DATA_DIR.iterdir()):
        if family_dir.is_dir():
            family_name = family_dir.name
            subfamilies = []
            
            # Find all subfamily directories
            for subfamily_dir in family_dir.iterdir():
                if subfamily_dir.is_dir():
                    subfamily_name = subfamily_dir.name
                    
                    # Include all font files in this subfamily
                    font_files = list(subfamily_dir.glob("*.woff2")) + list(subfamily_dir.glob("*.ttf")) + list(subfamily_dir.glob("*.otf")) + list(subfamily_dir.glob("*.woff"))
                    
                    if font_files:
                        # Try to read weight class from metadata file
                        weight_class = 400  # Default to Regular (400) if not found
                        metadata_path = subfamily_dir / "metadata.json"
                        if metadata_path.exists():
                            try:
                                with open(metadata_path, "r") as f:
                                    metadata = json.load(f)
                                    weight_class = metadata.get("weight_class", 400)
                            except Exception as e:
                                print(f"Error reading metadata for {subfamily_name}: {e}")
                        
                        subfamilies.append({
                            "name": subfamily_name,
                            "weight_class": weight_class,
                            "files": [
                                {
                                    "path": f"/fonts/{family_name}/{subfamily_name}/{f.name}",
                                    "type": f.suffix[1:],
                                    "is_preview": "_preview" in f.name
                                } for f in font_files
                            ]
                        })
            
            if subfamilies:
                # Find the "Regular" subfamily or default to the first one
                default_subfamily = next(
                    (sf for sf in subfamilies if sf["name"].lower() == "regular"), 
                    subfamilies[0] if subfamilies else None
                )
                
                fonts.append({
                    "name": family_name,
                    "subfamilies": subfamilies,
                    "default_subfamily": default_subfamily
                })
    
    return fonts

@app.post("/api/fonts/upload")
async def upload_font(file: UploadFile = File(...)):
    return await process_font_file(file)

@app.post("/api/fonts/upload-multiple")
async def upload_multiple_fonts(files: list[UploadFile] = File(...)):
    results = []
    for file in files:
        try:
            result = await process_font_file(file)
            results.append({"filename": file.filename, "success": True, "message": result["message"]})
        except HTTPException as e:
            results.append({"filename": file.filename, "success": False, "message": e.detail})
        except Exception as e:
            results.append({"filename": file.filename, "success": False, "message": str(e)})
    
    return {"results": results}

async def process_font_file(file: UploadFile):
    try:
        # Read the file into memory
        contents = await file.read()
        
        # Validate the font file
        try:
            font = TTFont(io.BytesIO(contents))
        except Exception as e:
            raise HTTPException(status_code=400, detail=f"Invalid font file format: {file.filename}")
                
        # Extract family name and subfamily
        familyName = None
        subfamily = None
        
        weightClass = font["OS/2"].usWeightClass

        for record in font['name'].names:
            if record.nameID == 1:  # Family Name
                familyName = record.toStr()
            if record.nameID == 16:  # Better Family Name
                familyName = record.toStr()
            if record.nameID == 2:  # Subfamily Name
                subfamily = record.toStr()
            if record.nameID == 17:  # Subfamily Name
                subfamily = record.toStr()
        
        # Use fallbacks if names not found in font
        if not familyName:
            familyName = os.path.splitext(file.filename)[0]
        if not subfamily:
            subfamily = "Regular"
            
        # Sanitize names for filesystem
        sanitized_family = "".join(c if c.isalnum() or c in "- " else "_" for c in familyName)
        sanitized_subfamily = "".join(c if c.isalnum() or c in "- " else "_" for c in subfamily)
        
        # Create directory structure: family/subfamily
        family_dir = DATA_DIR / sanitized_family
        family_dir.mkdir(exist_ok=True)
        
        subfamily_dir = family_dir / sanitized_subfamily
        
        # Check if subfamily already exists and contains font files
        if subfamily_dir.exists():
            font_files = list(subfamily_dir.glob("*.woff2")) + list(subfamily_dir.glob("*.ttf")) + list(subfamily_dir.glob("*.otf")) + list(subfamily_dir.glob("*.woff"))
            if font_files:
                return {"message": f"Subfamily '{subfamily}' already exists. File '{file.filename}' ignored."}
        
        # Create subfamily directory if it doesn't exist
        subfamily_dir.mkdir(exist_ok=True)
        
        # Use original filename for the font file
        font_name = os.path.splitext(file.filename)[0]
        font_dir = subfamily_dir
        
        # Save the original file
        file_path = font_dir / file.filename
        with open(file_path, "wb") as buffer:
            buffer.write(contents)
            
        # Save metadata with weight class
        metadata_path = font_dir / "metadata.json"
        metadata = {
            "weight_class": weightClass
        }
        with open(metadata_path, "w") as f:
            json.dump(metadata, f)
        
        # Convert to TTF if original is not TTF
        if file_path.suffix.lower() != '.ttf':
            ttf_path = font_dir / f"{font_name}.ttf"
            font.save(str(ttf_path))
        else:
            # If original is TTF, create a copy of the font object for OTF conversion
            ttf_path = file_path

        # Convert to OTF
        try:
            otf_path = font_dir / f"{font_name}.otf"
            otf_font = TTFont(str(ttf_path))
            otf_font.flavor = None  # Reset any flavor
            otf_font.save(str(otf_path))
        except Exception as e:
            print(f"Error converting to OTF: {e}")
         
        # Convert to WOFF
        try:
            woff_font = TTFont(io.BytesIO(contents))
            woff_path = font_dir / f"{font_name}.woff"
            woff_font.flavor = 'woff'
            woff_font.save(str(woff_path))
        except Exception as e:
            print(f"Error converting to WOFF: {e}")
        
        # Convert to WOFF2
        try:
            # Make sure we have a fresh font object
            woff2_font = TTFont(io.BytesIO(contents))
            woff2_path = font_dir / f"{font_name}.woff2"
            woff2_font.flavor = 'woff2'
            woff2_font.save(str(woff2_path))
            
            # Create a preview WOFF2 with subset of characters
            try:
                preview_font = TTFont(io.BytesIO(contents))
                # Define the characters to include in the subset
                subset_chars = "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789öäüß.,-_"
                
                # Create a subsetter
                subsetter = Subsetter()
                # Add the characters to the subsetter
                subsetter.populate(unicodes=[ord(c) for c in subset_chars])
                # Apply the subsetting
                subsetter.subset(preview_font)
                
                # Save as preview WOFF2
                preview_woff2_path = font_dir / f"{font_name}_preview.woff2"
                preview_font.flavor = 'woff2'
                preview_font.save(str(preview_woff2_path))
                print(f"Created preview WOFF2 with subset of characters: {preview_woff2_path}")
            except Exception as e:
                print(f"Error creating preview WOFF2: {e}")
        except Exception as e:
            print(f"Error converting to WOFF2: {e}")
            # Check if brotli is installed
            try:
                import brotli
            except ImportError:
                print("WOFF2 conversion requires the 'brotli' package. Please install it with 'pip install brotli'")
        
        return {"message": f"Font {file.filename} uploaded successfully"}
    except HTTPException as he:
        raise he
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000, reload=True)
