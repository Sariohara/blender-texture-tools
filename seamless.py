# -*- coding: utf-8 -*-

# ##### BEGIN GPL LICENSE BLOCK #####
#
#  This program is free software; you can redistribute it and/or
#  modify it under the terms of the GNU General Public License
#  as published by the Free Software Foundation; either version 2
#  of the License, or (at your option) any later version.
#
#  This program is distributed in the hope that it will be useful,
#  but WITHOUT ANY WARRANTY; without even the implied warranty of
#  MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#  GNU General Public License for more details.
#
#  You should have received a copy of the GNU General Public License
#  along with this program; if not, write to the Free Software Foundation,
#  Inc., 51 Franklin Street, Fifth Floor, Boston, MA 02110-1301, USA.
#
# ##### END GPL LICENSE BLOCK #####

bl_info = {
    "name": "Image Edit Operations",
    "category": "Paint",
    "description": "Various image processing filters and operations",
    "author": "Tommi Hyppänen (ambi)",
    "location": "Image Editor > Tool Shelf > Texture Tools",
    "documentation": "http://blenderartists.org/forum/showthread.php?364409-WIP-Seamless-texture-patching-addon",
    "version": (0, 1, 7),
    "blender": (2, 73, 0)
}

import bpy
import numpy

#### IMAGE OPERATIONS

class GeneralImageOperator(bpy.types.Operator):
    def init_images(self, context):
        self.input_image = context.scene.seamless_input_image
        self.target_image = context.scene.seamless_generated_name
        self.seamless_powersoftwo = bpy.context.scene.seamless_powersoftwo
        
        print("Creating images...")
        self.size = bpy.data.images[self.input_image].size
        self.xs = self.size[0]
        self.ys = self.size[1]

        # copy image data into much more performant numpy arrays
        self.sourcepixels = numpy.array(bpy.data.images[self.input_image].pixels)
        self.sourcepixels = self.sourcepixels.reshape((self.ys,self.xs,4))

        # if limit to powers of two is selected, do it
        offx = 0
        offy = 0
        if self.seamless_powersoftwo:
            print("crop to 2^")
            lxs = int(numpy.log2(self.xs))
            lys = int(numpy.log2(self.ys))
            offx = int((self.xs-2**lxs)/2)
            offy = int((self.ys-2**lys)/2)
            print("crop offset:"+repr(offx)+","+repr(offy))

            if self.xs > 2**lxs:
                self.xs = 2**lxs
            if self.ys > 2**lys:
                self.ys = 2**lys

        # crop to center
        self.sourcepixels = self.sourcepixels[offy:offy+self.ys,offx:offx+self.xs]
        print("sshape:"+repr(self.sourcepixels.shape))

        # if target image exists, change the size to fit
        if self.target_image in bpy.data.images:
            bpy.data.images[self.target_image].scale(self.xs, self.ys)
            self.image = bpy.data.images[self.target_image]
        else:
            self.image = bpy.data.images.new(self.target_image, width=self.xs, height=self.ys)

        self.pixels = numpy.zeros((self.ys,self.xs,4))
        self.pixels[:,:,3] = 1.0 # alpha is always 1.0 everywhere
        
        print("Start iteration")     
        
    def finish_images(self, context):
        print("Assign data")
        # assign pixels
        self.image.pixels = self.pixels.flatten()    
        bpy.ops.image.invert(invert_r=False, invert_g=False, invert_b=False, invert_a=False)

def convolution(ssp, intens, sfil):    
    # source, intensity, convolution matrix    
    tpx = numpy.zeros(ssp.shape, dtype=float)
    tpx[:,:,3] = 1.0
    ystep = int(4*ssp.shape[1])
    norms = 0
    for y in range(sfil.shape[0]):
        for x in range(sfil.shape[1]):
            tpx += numpy.roll(ssp, (x-int(sfil.shape[1]/2))*4 + (y-int(sfil.shape[0]/2))*ystep) * sfil[y,x]
            norms += sfil[y,x]
    if norms > 0:
        tpx /= norms
    return ssp + (tpx-ssp) * intens

def normalize(arr):
    # vec *= 1/len(vec)
    m = 1.0/numpy.sqrt(arr[:,:,0]**2 + arr[:,:,1]**2 + arr[:,:,2]**2)
    arr[...,0] *= m
    arr[...,1] *= m
    arr[...,2] *= m
    return arr

class ConvolutionsOperator(GeneralImageOperator):
    """Image filter operator"""
    bl_idname = "uv.image_convolutions"
    bl_label = "Convolution filters"

    def filter_blur(self, s, intensity):
        self.pixels = convolution(self.sourcepixels, intensity, numpy.ones((1+s*2, 1+s*2), dtype=float))

    def filter_sharpen(self, s, intensity): 
        self.pixels = convolution(self.sourcepixels, intensity, numpy.array( \
            [[  -1,  -1,  -1],
             [  -1,   9,  -1],
             [  -1,  -1,  -1]]))

    def _normalize(img):
        t = img - numpy.min(img)
        return t / numpy.max(t)

    def _filter_sobel_x(source, intensity):
        gx = numpy.array( \
            [[  -1,   0,   1],
             [  -2,   0,   2],
             [  -1,   0,   1]])  
        return convolution(source, 1.0, gx) * intensity
        
    def _filter_sobel_y(source, intensity):
        gy = numpy.array( \
            [[   1,   2,   1],
             [   0,   0,   0],
             [  -1,  -2,  -1]])
        return convolution(source, 1.0, gy) * intensity

    def _box_clamp(x1, y1, x2, y2, minx, miny, maxx, maxy):
        if x1 < minx:
            x1 = minx
        if x2 > maxx:
            x2 = maxx
        if y1 < miny:
            y1 = miny
        if y2 > maxy:
            y2 = maxy
        return (x1,y1,x2,y2)

    def filter_edgedetect(self, s, intensity):
        self.pixels = (convolution(self.sourcepixels, intensity, numpy.array( \
            [[   0,   1,   0],
             [   1,  -4,   1],
             [   0,   1,   0]])))*0.5+0.5            

    def filter_emboss(self, s, intensity):
        self.pixels = convolution(self.sourcepixels, intensity, numpy.array( \
            [[  -2,   1,   0],
             [  -1,   1,   1],
             [   0,   1,   2]]))

    def filter_gaussian(self, s, intensity):
        fil = numpy.ones((1+s*2, 1+s*2), dtype=float)
        a = 1.0/numpy.sqrt(2*numpy.pi)
        xs = int(fil.shape[1]/2)
        ys = int(fil.shape[0]/2)
        ro = 5.0 ** 2
        for y in range(0, fil.shape[0]):
            for x in range(0, fil.shape[1]):
                fil[y,x] =  (1.0/numpy.sqrt(2*numpy.pi*ro)) * (2.71828 ** (-((x-xs)**2 + (y-ys)**2)/(2*ro)))
        self.pixels = convolution(self.sourcepixels, intensity, fil)

    def filter_fast_gaussian(self, s, intensity):
        d = 2 ** s
        tpx = self.sourcepixels
        ystep = tpx.shape[1]
        while d > 1:
            tpx = (tpx*2 + numpy.roll(tpx,-d*4) + numpy.roll(tpx, d*4))/4
            tpx = (tpx*2 + numpy.roll(tpx,-d*(ystep*4)) + numpy.roll(tpx, d*(ystep*4)))/4
            d = int(d/2)
        self.pixels = tpx

    def filter_normals_simple(self, s, intensity):
        gradx = ConvolutionsOperator._filter_sobel_x(self.sourcepixels, 1.0) 
        gradx[:,:,2] = (gradx[:,:,0] + gradx[:,:,1] + gradx[:,:,2])*intensity/3
        gradx[:,:,1] = 0
        gradx[:,:,0] = 1

        grady = ConvolutionsOperator._filter_sobel_y(self.sourcepixels, 1.0) 
        grady[:,:,2] = (grady[:,:,0] + grady[:,:,1] + grady[:,:,2])*intensity/3
        grady[:,:,1] = 1
        grady[:,:,0] = 0

        vectors = normalize(numpy.cross(gradx[:,:,:3], grady[:,:,:3]))

        self.pixels[:,:,0] = 0.5 - vectors[:,:,0]
        self.pixels[:,:,1] = vectors[:,:,1] + 0.5
        self.pixels[:,:,2] = vectors[:,:,2]
        self.pixels[:,:,3] = 1.0

    def filter_sobel(self, s, intensity):
        self.pixels = ConvolutionsOperator._filter_sobel_x(self.sourcepixels, 1.0) 
        self.pixels+= ConvolutionsOperator._filter_sobel_y(self.sourcepixels, 1.0) 
        self.pixels = (self.pixels * intensity)*0.5+0.5
        self.pixels[:,:,3] = 1.0

    def filter_poisson_blending(self, s, intensity):
        b = numpy.copy(self.sourcepixels)
        b[1:-1, 1:-1] = [0,0,0,0]
        b[-1,:] = b[0,:] - b[-1,:]
        b[0,:] = [0,0,0,0]
        b[:,-1] = b[:,0] - b[:,-1]
        b[:,0] = [0,0,0,0]

        u = numpy.copy(b)
        u[1:-1,1:-1] = (numpy.zeros(b.shape))[1:-1,1:-1]

        # solve poisson
        for i in range(200):
            u[1:-1,1:-1] = (u[0:-2,1:-1] + u[2:,1:-1] +
                 u[1:-1,0:-2] + u[1:-1,2:] + b[1:-1,1:-1])/4            

        self.pixels =  u + self.sourcepixels

    def filter_separate_values(self, s, intensity):
        self.pixels[...,:3] = self.sourcepixels[...,:3] ** intensity

    def filter_grayscale(self, s, intensity):
        ssp = self.sourcepixels
        r, g, b = ssp[:,:,0], ssp[:,:,1], ssp[:,:,2]
        gray = 0.2989 * r + 0.5870 * g + 0.1140 * b
        self.pixels[...,0] = gray
        self.pixels[...,1] = gray
        self.pixels[...,2] = gray

    def filter_bilateral(self, s, intensity): 
        ssp = self.sourcepixels
        pix = numpy.copy(ssp)
        ystep = ssp.shape[1]*4
        nr = numpy.roll

        b = numpy.abs(ConvolutionsOperator._filter_sobel_x(ssp, 1.0))
        b+= numpy.abs(ConvolutionsOperator._filter_sobel_y(ssp, 1.0))
        # smooth
        for _ in range(3):
            b = (nr(b,4)+nr(b,-4)+nr(b,ystep)+nr(b,-ystep)+b)/5

        b **= intensity
        b[...,3] = 1.0

        ssx = ssp.shape[1]
        ssy = ssp.shape[0]
        for y in range(0,ssy):
            for x in range(0,ssx):
                m = numpy.sum(b[y,x][:3])/3
                si = 1+int(numpy.abs((1-m)*2*s))
                a = numpy.array(ssp[y,x], dtype=float)

                x1,y1,x2,y2 = ConvolutionsOperator._box_clamp(x-si, y-si, x+si+1, y+si+1, 0, 0, ssx-1, ssy-1)
                if x1<x2 and y1<y2:
                    #blockmul =  numpy.abs(1-b[y1:y2, x1:x2])
                    block = ssp[y1:y2, x1:x2]# * blockmul
                    a[0] = numpy.median(block[...,0])
                    a[1] = numpy.median(block[...,1])
                    a[2] = numpy.median(block[...,2])

                pix[y,x] = ssp[y,x]*m +  a* (1-m)
        pix[...,3] = 1.0
        self.pixels = pix


    def calculate(self, context):     
        self.selected_filter(context.scene.seamless_filter_size, context.scene.seamless_filter_intensity)

    def execute(self, context):
        self.selected_filter = {
            "BLUR":self.filter_blur,
            "EDGEDETECT":self.filter_edgedetect,
            "SHARPEN":self.filter_sharpen,
            "GAUSSIAN":self.filter_gaussian,
            "FASTGAUSSIAN":self.filter_fast_gaussian,
            "SOBEL":self.filter_sobel,
            "NORMALSSIMPLE":self.filter_normals_simple,
            "SEPARATEVALUES":self.filter_separate_values,
            "POISSONTILES":self.filter_poisson_blending,
            "BILATERAL":self.filter_bilateral,
            "GRAYSCALE":self.filter_grayscale,
            "EMBOSS":self.filter_emboss } \
            [context.scene.seamless_filter_type]
        self.init_images(context)
        self.calculate(context)
        self.finish_images(context)
                
        return {'FINISHED'}  

class GimpSeamlessOperator(GeneralImageOperator):
    # TODO: the smoothing is not complete, it goes only one way
    """Image seamless generator operator"""
    bl_idname = "uv.gimp_seamless_operator"
    bl_label = "Gimp-style Image Seamless Operator"

    def gimpify(self):
        self.pixels = numpy.copy(self.sourcepixels)
        self.sourcepixels = numpy.roll(self.sourcepixels,self.xs*2+self.xs*4*int(self.ys/2))

        # margin = self.seamless_gimpmargin
        # if margin>self.xs:
        #     margin = int(self.xs)

        sxs = int(self.xs/2)
        sys = int(self.ys/2)

        # generate the mask
        print(self.pixels.shape)
        imask = numpy.zeros((self.pixels.shape[0], self.pixels.shape[1]), dtype=float) 
        for y in range(0, sys):
            zy0 = y/sys+0.001
            zy1 = 1-y/sys+0.001
            for x in range(0, sxs):
                zx0 = 1-x/sxs+0.001
                imask[y,x] = (1-zy0/zx0)
                zx1 = x/sxs+0.001
                imask[y,x] = numpy.maximum((1-zx1/zy1), imask[y,x])

        imask[imask<0] = 0

        # copy the data into the three remaining corners
        imask[0:self.ys/2+1, self.xs/2:self.xs-1] = numpy.fliplr(imask[0:self.ys/2+1, 0:self.xs/2-1])
        imask[-self.ys/2:self.ys, 0:self.xs/2] = numpy.flipud(imask[0:self.ys/2, 0:self.xs/2])
        imask[-self.ys/2:self.ys, self.xs/2:self.xs-1] = numpy.flipud(imask[0:self.ys/2, self.xs/2:self.xs-1])
        imask[self.ys/2,:] = imask[self.ys/2-1,:] # center line

        # apply mask
        amask = numpy.zeros(self.pixels.shape, dtype=float)
        amask[:,:,0] = imask 
        amask[:,:,1] = imask
        amask[:,:,2] = imask
        amask[:,:,3] = 1.0

        self.pixels = amask * self.sourcepixels + (numpy.ones(amask.shape) - amask) * self.pixels
        #self.pixels = amask

    def execute(self, context):
        self.init_images(context)
        self.seamless_gimpmargin = context.scene.seamless_gimpmargin
        self.gimpify()
        self.finish_images(context)
                
        return {'FINISHED'}  

class SeamlessOperator(GeneralImageOperator):
    """Image seamless texture patcher operator"""
    bl_idname = "uv.seamless_operator"
    bl_label = "Image Seamless Operator"

    maxSSD = 100000000

    def SSD(self,b1,b2):
        if b1.shape == b2.shape:
            return numpy.sum(((b1-b2)*[0.2989, 0.5870, 0.1140, 0.0])**2)
        else:
            return self.maxSSD

    def stitch(self,x,y):
        dimage = self.pixels
        simage = self.sourcepixels

        winx = self.seamless_window
        winy = self.seamless_window
        
        if winx + x > self.xs or winy + y > self.ys:
            return
            
        sxs = self.xs - winx
        sys = self.ys - winy
        
        bestx,besty = self.seamless_window,self.seamless_window
        bestresult = self.maxSSD
        b1 = dimage[y:y+winy, x:x+winx,:]
        
        # only test for pixels where the alpha is not zero
        # alpha 0.0 signifies no data, the area to be filled by patching
        # alpha 1.0 is the source data plus the already written patches
        indices = numpy.where(b1[:,:,3]>0)
        
        # random sample through the entire source data to find the best match
        for i in range(self.seamless_samples):
            temx = numpy.random.randint(sxs)
            temy = numpy.random.randint(sys)
            b2 = simage[temy:temy+winy,temx:temx+winx,:]
            result = self.SSD(b1[indices], b2[indices])
            if result < bestresult:
                bestresult = result
                bestx, besty = temx, temy
                
        batch = numpy.copy(simage[besty:besty+winy,bestx:bestx+winx,:])
                
        if self.seamless_smoothing and winx == self.seamless_window and winy == self.seamless_window: 
            # image edge patches can't have a mask because they are irregular shapes
            mask = numpy.ones((winx, winy))
            for i in range(int(self.seamless_overlap/2)):
                val = float(i)/float(self.seamless_overlap/2)
                mask[i,:] *= val
                mask[winy-i-1,:] *= val
                mask[:,i] *= val
                mask[:,winx-i-1] *= val            
            
            mask[numpy.where(b1[:,:,3]<0.5)] = 1.0
            #mask[indices] = 1.0
            batch[:,:,0] = dimage[y:y+winy, x:x+winx,0]*(1.0-mask) + batch[:,:,0]*mask
            batch[:,:,1] = dimage[y:y+winy, x:x+winx,1]*(1.0-mask) + batch[:,:,1]*mask
            batch[:,:,2] = dimage[y:y+winy, x:x+winx,2]*(1.0-mask) + batch[:,:,2]*mask
            batch[:,:,3] = 1.0

        # copy the new patch to the image
        dimage[y:y+winy, x:x+winx,:] = batch
        
    def patch_iterate(self):
        # offset both x and y half the size of the image (put edges on center)
        self.pixels = numpy.roll(self.sourcepixels,self.xs*2+self.xs*4*int(self.ys/2))

        step = self.seamless_window-self.seamless_overlap
        margin = step * self.seamless_lines - self.seamless_overlap
        
        # erase the data from the are we are about to fill with patches
        self.pixels[int(self.ys/2-margin/2):int(self.ys/2+margin/2),:,:] = [0.0,0.0,0.0,0.0]
        self.pixels[:,int(self.xs/2)-margin/2:int(self.xs/2)+margin/2,:] = [0.0,0.0,0.0,0.0]
        
        xmax = int(self.xs-1)
        ymax = int(self.ys-1)
        
        # reconstruct the missing area with patching
        xstart = int(self.xs/2)-margin/2-self.seamless_overlap
        ystart = int(self.ys/2)-margin/2-self.seamless_overlap

        for _ in range(1):
            #horizontal
            for x in range(0, xmax, step):
                for y in range(0, self.seamless_lines):
                    self.stitch(x,y*step+ystart)

            #vertical
            for y in range(0, ymax, step):
                for x in range(0, self.seamless_lines):
                    self.stitch(x*step+xstart,y)       
                    
        # fill in the last edge cases
        self.pixels = numpy.roll(self.pixels,self.xs*2) # half x offset
        for y in range(0, self.seamless_lines):
            self.stitch(int(self.xs/2)-step,y*step+ystart)
        self.pixels = numpy.roll(self.pixels,self.xs*2) # half x offset
        self.pixels = numpy.roll(self.pixels,self.xs*4*int(self.ys/2)) # half y offset
        for x in range(0, self.seamless_lines):
            self.stitch(x*step+xstart,int(self.ys/2)-step)  
        self.pixels = numpy.roll(self.pixels,self.xs*4*int(self.ys/2)) # half y offset

    def execute(self, context):
        self.init_images(context)

        self.seamless_samples = bpy.context.scene.seamless_samples
        self.seamless_window = bpy.context.scene.seamless_window
        self.seamless_overlap = bpy.context.scene.seamless_overlap
        self.seamless_lines = bpy.context.scene.seamless_lines
        self.seamless_smoothing = bpy.context.scene.seamless_smoothing

        self.patch_iterate()
        self.finish_images(context)
                
        return {'FINISHED'}    

class MaterialTextureGenerator(bpy.types.Operator):
    bl_idname = "uv.material_texgen"
    bl_label = "Generate textures for a material"
        
    def execute(self, context):
        self.input_material = context.scene.seamless_input_material
        self.input_image = bpy.data.images[context.scene.seamless_input_image]

        self.xs = self.input_image.size[0]
        self.ys = self.input_image.size[1]

        print("Assign data")
        print(repr(self.input_material))
        mat = bpy.data.materials[self.input_material]
        textures = []
        for t in mat.texture_slots.values():
            if t:
                textures.append(t)
                print(t)
        print(textures)
        matn = self.input_material

        difftex = matn+'_t_d'
        normtex = matn+'_t_n'
        spectex = matn+'_t_s'

        diffimg = matn+'_d'
        normimg = matn+'_n'
        specimg = matn+'_s'

        bpy.data.textures.new(difftex, 'IMAGE')
        bpy.data.textures.new(normtex, 'IMAGE')
        bpy.data.textures.new(spectex, 'IMAGE')

        # GENERATE DIFFUSE
        bpy.data.textures[difftex].image = bpy.data.images.new(diffimg, width=self.xs, height=self.ys)
        sourcepixels = numpy.array(self.input_image.pixels).reshape((self.ys,self.xs,4))
        bpy.data.textures[difftex].image.pixels = sourcepixels.flatten() 

        # GENERATE NORMALS
        bpy.data.textures[normtex].image = bpy.data.images.new(normimg, width=self.xs, height=self.ys)
        bpy.data.textures[normtex].use_normal_map = True
        
        # copy image data into much more performant numpy arrays
        sourcepixels = numpy.array(self.input_image.pixels).reshape((self.ys,self.xs,4))
        pixels = numpy.ones((self.ys,self.xs,4))

        gradx = ConvolutionsOperator._filter_sobel_x(sourcepixels, 1.0) 
        gradx[:,:,2] = (gradx[:,:,0] + gradx[:,:,1] + gradx[:,:,2])/3
        gradx[:,:,1] = 0
        gradx[:,:,0] = 1

        grady = ConvolutionsOperator._filter_sobel_y(sourcepixels, 1.0) 
        grady[:,:,2] = (grady[:,:,0] + grady[:,:,1] + grady[:,:,2])/3
        grady[:,:,1] = 1
        grady[:,:,0] = 0

        vectors = normalize(numpy.cross(gradx[:,:,:3], grady[:,:,:3]))

        pixels[:,:,0] = 0.5 - vectors[:,:,0]
        pixels[:,:,1] = vectors[:,:,1] + 0.5
        pixels[:,:,2] = vectors[:,:,2]
        pixels[:,:,3] = 1.0
        
        # assign pixels
        bpy.data.textures[normtex].image.pixels = pixels.flatten()    
            
        # GENERATE SPEC
        bpy.data.textures[spectex].image = bpy.data.images.new(specimg, width=self.xs, height=self.ys)

        ssp = numpy.array(self.input_image.pixels).reshape((self.ys,self.xs,4))
        pixels = numpy.ones((self.ys,self.xs,4))
        r, g, b = ssp[:,:,0], ssp[:,:,1], ssp[:,:,2]
        gray = 0.2989 * r + 0.5870 * g + 0.1140 * b
        gray **= 4
        gray = gray - numpy.min(gray)
        gray/= numpy.max(gray)
        pixels[...,0] = gray
        pixels[...,1] = gray
        pixels[...,2] = gray
        bpy.data.textures[spectex].image.pixels = pixels.flatten()    

        bpy.ops.image.invert(invert_r=False, invert_g=False, invert_b=False, invert_a=False)

        bpy.data.materials[matn].specular_hardness = 30
        bpy.data.materials[matn].specular_intensity = 0
        for i in range(3):
            bpy.data.materials[matn].texture_slots.create(i)
        bpy.data.materials[matn].texture_slots[0].texture = bpy.data.textures[difftex]
        bpy.data.materials[matn].texture_slots[1].texture = bpy.data.textures[normtex]
        bpy.data.materials[matn].texture_slots[1].use_map_color_diffuse = False
        bpy.data.materials[matn].texture_slots[1].use_map_normal = True
        bpy.data.materials[matn].texture_slots[1].normal_factor = 0.5
        bpy.data.materials[matn].texture_slots[2].texture = bpy.data.textures[spectex]
        bpy.data.materials[matn].texture_slots[2].use_map_color_diffuse = False
        bpy.data.materials[matn].texture_slots[2].texture.use_alpha = False
        bpy.data.materials[matn].texture_slots[2].use_map_specular = True
   
        return {'FINISHED'}    

#### USER INTERFACE
    
class TextureToolsPanel(bpy.types.Panel):
    bl_space_type = 'IMAGE_EDITOR'
    bl_region_type = 'TOOLS'
    bl_label = "Seamless Patching"
    bl_category = "Texture Tools"

    def draw(self, context):
        layout = self.layout

        row = layout.row()
        row.label("Patched:")

        row = layout.row()
        row.prop(context.scene, "seamless_samples")
        row.prop(context.scene, "seamless_window")

        row = layout.row()
        row.prop(context.scene, "seamless_overlap")
        row.prop(context.scene, "seamless_lines")
        
        row = layout.row()
        row.prop(context.scene, "seamless_smoothing")

        row = layout.row()
        row.operator(SeamlessOperator.bl_idname, text="Make seamless (patches)")

        row = layout.row()
        row.label("Fast and simple:")
                
        # row = layout.row()
        # row.prop(context.scene, "seamless_gimpmargin")
        
        row = layout.row()
        row.operator(GimpSeamlessOperator.bl_idname, text="Make seamless (fast)")

class TextureToolsFiltersPanel(bpy.types.Panel):
    bl_space_type = 'IMAGE_EDITOR'
    bl_region_type = 'TOOLS'
    bl_label = "Image Filters"
    bl_category = "Texture Tools"

    def draw(self, context):
        layout = self.layout
        row = layout.row()
        row.prop(context.scene, "seamless_filter_type")

        row = layout.row()
        row.prop(context.scene, "seamless_filter_size")
        row.prop(context.scene, "seamless_filter_intensity")

        row = layout.row()
        row.operator(ConvolutionsOperator.bl_idname, text="Filter")

class TextureToolsMaterialsPanel(bpy.types.Panel):
    bl_space_type = 'IMAGE_EDITOR'
    bl_region_type = 'TOOLS'
    bl_label = "Material Tools"
    bl_category = "Texture Tools"

    def draw(self, context):
        layout = self.layout
        # row = layout.row()
        # row.label("In a material world.")

        row = layout.row()
        row.prop(context.scene, "seamless_input_material")

        row = layout.row()
        row.operator(MaterialTextureGenerator.bl_idname, text="Generate textures")

class TextureToolsImageSelectionPanel(bpy.types.Panel):
    bl_space_type = 'IMAGE_EDITOR'
    bl_region_type = 'TOOLS'
    bl_label = "Image Selection"
    bl_category = "Texture Tools"

    def draw(self, context):
        layout = self.layout

        row = layout.row()
        row.prop(context.scene, "seamless_input_image")

        row = layout.row()
        row.prop(context.scene, "seamless_generated_name")

        row = layout.row()
        row.prop(context.scene, "seamless_powersoftwo")

#### NODE SYSTEM

class ImageEditNodeTree(bpy.types.NodeTree):
    bl_idname = 'ImageTreeType'
    bl_label = 'Image Edit Node Tree'
    bl_icon = 'COLOR'

class ImageInputNode(bpy.types.Node):
    bl_idname = 'ImageInputNodeType'
    bl_label = 'Image Input Node'
    bl_icon = 'SOUND'

    my_input_value = bpy.props.FloatProperty(name="Size", default=5.0, subtype="FACTOR")

    @classmethod
    def poll(cls, tree):
        return tree.bl_idname == 'ImageTreeType'

    def init(self, context):
        my_input = self.inputs.new("NodeSocketFloat", "My Input")
        my_input.value_property = "my_input_value"

#### INITIALIZATION

def register():
    # SEAMLESS PANEL
    bpy.types.Scene.seamless_samples = bpy.props.IntProperty(name="Samples", default=100, min=1, max=10000)
    bpy.types.Scene.seamless_window = bpy.props.IntProperty(name="Window", default=32, min=2, max=128)
    bpy.types.Scene.seamless_overlap = bpy.props.IntProperty(name="Overlap", default=8, min=1, max=64)
    bpy.types.Scene.seamless_lines = bpy.props.IntProperty(name="Lines", default=2, min=1, max=16)
    bpy.types.Scene.seamless_gimpmargin = bpy.props.IntProperty(name="Blending margin", default=200, min=1, max=1000)
    bpy.types.Scene.seamless_smoothing = bpy.props.BoolProperty(name="Patch smoothing")

    available_objects = []
    def availableObjects(self, context):
        available_objects.clear()
        for im in bpy.data.images:
            name = im.name
            available_objects.append((name, name, name))
        return available_objects

    # IMAGE SELECTION & TOOLS
    bpy.types.Scene.seamless_generated_name = bpy.props.StringProperty(name="Output image", default="generated")
    bpy.types.Scene.seamless_input_image = bpy.props.EnumProperty(name="Input image", items=availableObjects)
    bpy.types.Scene.seamless_powersoftwo = bpy.props.BoolProperty(name="Crop to powers of two")

    # FILTER PANEL
    bpy.types.Scene.seamless_filter_type = bpy.props.EnumProperty(name="Filter type", items=[
        ("BLUR", "Box blur", "", 1),
        ("SHARPEN", "Sharpen", "", 2),
        ("EDGEDETECT", "Edge detect", "", 3),
        ("EMBOSS", "Emboss", "", 4),
        ("GAUSSIAN", "Gaussian blur ro:5", "", 5),
        ("FASTGAUSSIAN", "Fast gaussian", "", 6),
        ("SOBEL", "Sobel", "", 7),
        ("NORMALSSIMPLE", "Normal map: simple", "", 8),
        ("SEPARATEVALUES", "Emphasize whites or blacks", "", 9),
        ("POISSONTILES", "Blend image edges", "", 10),
        ("BILATERAL", "Bilateral blur", "", 11),
        ("GRAYSCALE", "Grayscale", "", 12),    
        ])
    bpy.types.Scene.seamless_filter_size = bpy.props.IntProperty(name="Size", default=1, min=1, max=9)
    bpy.types.Scene.seamless_filter_intensity = bpy.props.FloatProperty(name="Intensity", default=1.0, min=0.0, max=3.0)

    # MATERIALS PANEL
    available_materials = []
    def availableMaterials(self, context):
        available_materials.clear()
        for im in bpy.data.materials:
            name = im.name
            available_materials.append((name, name, name))
        return available_materials
    bpy.types.Scene.seamless_input_material = bpy.props.EnumProperty(name="Material", items=availableMaterials)

    # register classes
    regclasses = [SeamlessOperator, GimpSeamlessOperator, ConvolutionsOperator, TextureToolsImageSelectionPanel, TextureToolsPanel, 
                  TextureToolsFiltersPanel, TextureToolsMaterialsPanel, MaterialTextureGenerator, 
                  ImageEditNodeTree, ImageInputNode]

    for entry in regclasses:
        bpy.utils.register_class(entry)

def unregister():
    for entry in regclasses:
        bpy.utils.unregister_class(entry)

if __name__ == "__main__":
    register()

#### ~~~ DOCUMENTATION ~~~
    # stuff I want done:

    # Progress bar

    # ??? drag & drop from google images

    # Normal/diffuse/height/cavitymap extraction from bitmap data

    #--------------------------

    # drag & drop
    # import urllib
    # urllib.urlretrieve ("http://www.example.com/songs/mp3.mp3", "mp3.mp3")

    # import urllib2
    # mp3file = urllib2.urlopen("http://www.example.com/songs/mp3.mp3")
    # output = open('test.mp3','wb')
    # output.write(mp3file.read())
    # output.close()

    # -------- FUTURE TOOLS:
    # Lighting Lighting_balance
    # Normalize
    # Offset by half

    # Dilate
    # Erode