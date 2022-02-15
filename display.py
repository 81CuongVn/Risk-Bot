from PIL import Image, ImageDraw
import io

points = {
"Alaska":(44, 94),
"North West Territory":(125, 86),
"Greenland":(268, 59),
"Alberta":(112, 136),
"Ontario":(155, 122),
"Quebec":(206, 151),
"Western United States":(109, 199),
"Eastern United States":(195, 188),
"Central America":(135, 253),
"Venezuela":(170, 288),
"Peru":(172, 371),
"Brazil":(243, 375),
"Argentina":(190, 457),
"Iceland":(329, 114),
"Scandinavia":(393, 122),
"Ukraine":(457, 164),
"Great Britain":(326, 179),
"Northern Europe":(371, 194),
"Western Europe":(340, 260),
"Southern Europe":(380, 234),
"North Africa":(359, 316),
"Egypt":(425, 326),
"East Africa":(452, 351),
"Congo":(431, 421),
"South Africa":(429, 498),
"Madagascar":(493, 475),
"Ural":(553, 145),
"Siberia":(597, 101),
"Yakutsk":(644, 77),
"Kamchatka":(702, 82),
"Irkutsk":(635, 145),
"Mongolia":(648, 197),
"Japan":(723, 207),
"Afghanistan":(536, 214),
"China":(644, 252),
"Middle East":(489, 305),
"India":(583, 302),
"Siam":(661, 317),
"Indonesia":(656, 414),
"New Guinea":(733, 392),
"Western Australia":(689, 452),
"Eastern Australia":(762, 485)}

def draw_map(game):
  with Image.open("map.jpg") as im:
  
    draw = ImageDraw.Draw(im)

    territories = game["territories"]

    for name in territories.keys():
      point = points[name]
      point_box = (point[0]-7, point[1]-7, point[0]+7, point[1]+7)
      
      owner = str(territories[name]["owner"])
      if owner != "None":
        colour = game["players"][owner]["colour"]
        if colour == "red":
          colour = (200, 0, 0)
        elif colour == "blue":
          colour = (0, 0, 128)
        elif colour == "yellow":
          colour = (255, 245, 0)
        elif colour == "green":
          colour = (0, 128, 0)
        elif colour == "brown":
          colour = (110, 38, 10)
        elif colour == "black":
          colour = (0, 0, 0)
      else:
        colour = (128, 128, 128)
      
      draw.ellipse(point_box, fill=colour)
      troop_count = territories[name]["troops"]
      draw.text((point_box[0] + 2 + (0 if troop_count > 9 else 3), point_box[1] + 2), str(troop_count), font=draw.getfont(), fill=((0, 0, 0) if colour == (255, 245, 0) else (255, 255, 255)))

    byte_arr = io.BytesIO()
    im.save(byte_arr, format="JPEG")
    byte_arr.seek(0)

    return byte_arr